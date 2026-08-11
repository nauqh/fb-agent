"""What is queued to go out, read live from Metricool.

**There is no schedule table and there will not be one** (ADR-0001). The old
system mirrored every scheduled post into `facebook_schedules`, with a five-value
status enum, a due-post cron and a stale-`PROCESSING` recovery path; production
held 0 rows against 237 approved drafts. Posts are scheduled, moved and
cancelled in Metricool's planner — including by hand, in Metricool's own UI, by
somebody who has never heard of this app — so a local copy could only ever
disagree with the truth.

The cost is stated plainly in the ADR: this screen needs a network call and is
unavailable when Metricool is. That is the correct failure. An empty calendar
drawn from a stale mirror is worse than one that says it cannot reach the
planner.
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session, select

from app.db import get_session
from app.models import Draft, Page, PageTimeSlot
from app.publish import metricool as publisher
from app.settings import settings

router = APIRouter(tags=["schedule"])


class ScheduledPost(BaseModel):
    """One row of Metricool's planner, flattened.

    Deliberately not a `Draft`. Most of these were never drafts of ours — 302 of
    them were queued by the old system, which is still the thing publishing
    History Retraced. Mapping them onto our own model would invent fields
    (`hook`, `highlight_phrases`) that do not exist for a post somebody wrote in
    Metricool's composer.
    """

    id: str
    published_at: str
    """Naive local time, exactly as Metricool stores it. Not converted to UTC:
    the planner's times *are* local times, and re-anchoring them to an instant
    would move every row by the offset."""

    timezone: str
    text: str
    first_comment: str | None = None
    image_url: str | None = None
    network: str = "facebook"
    status: str
    """`PUBLISHED`, `PENDING`, `ERROR` — Metricool's word, not ours."""

    public_url: str | None = None
    is_draft: bool = False
    draft_id: int | None = None
    """Ours, when the post came from this app. Null for everything the old
    system queued, which is how the two are told apart during the cutover."""


def _flatten(row: dict, ours: dict[str, int]) -> ScheduledPost:
    providers = row.get("providers") or [{}]
    provider = providers[0]
    media = row.get("media") or []
    post_id = str(row.get("id", ""))

    return ScheduledPost(
        id=post_id,
        published_at=(row.get("publicationDate") or {}).get("dateTime", ""),
        timezone=(row.get("publicationDate") or {}).get("timezone", ""),
        text=row.get("text") or "",
        first_comment=row.get("firstCommentText") or None,
        image_url=media[0] if media else None,
        network=provider.get("network") or "facebook",
        # A draft in the planner has no provider status at all, and reporting
        # that as blank makes it look broken rather than unsent.
        status=provider.get("status") or ("DRAFT" if row.get("draft") else "PENDING"),
        public_url=provider.get("publicUrl"),
        is_draft=bool(row.get("draft")),
        draft_id=ours.get(post_id),
    )


class NextSlot(BaseModel):
    """The next configured time with nothing already queued against it."""

    when: str
    """Naive local time, `YYYY-MM-DDTHH:MM:SS`, in the Page's zone — the same
    shape `POST /drafts/{id}/publish` takes and the planner stores."""

    label: str
    """`HH:MM`, the slot as it is configured."""

    taken: int
    """How many slots were skipped because the planner already has a post at
    them. Shown so "why is it offering Thursday" answers itself."""


SLOT_SEARCH_DAYS = 30
"""How far forward to look before giving up. A Page with three slots a day and a
full month queued is not a case to solve by searching further."""


@router.get("/schedule/next-slot")
def next_slot(
    page_id: int = Query(1),
    session: Session = Depends(get_session),
) -> NextSlot:
    """The next publishing time this Page has free.

    Walks forward from now through the Page's configured slots and returns the
    first that Metricool's planner has nothing at. **The planner is the only
    thing consulted about what is taken** (ADR-0001) — there is no local mirror
    to disagree with, and a post somebody scheduled by hand in Metricool's own
    UI counts exactly as much as one of ours.

    A slot is "taken" when the planner holds any post whose local time falls in
    the same minute. Minute precision rather than exact-string equality because
    the planner's own times come back as naive local strings and a post moved by
    hand can land a second off; and rather than a wider window, because two
    slots an hour apart must not shadow each other.

    Times are naive local throughout — `publicationDate.dateTime` is naive local
    and an offset suffix is rejected, which is the trap `CLAUDE.md` records.
    """
    page = session.get(Page, page_id)
    if page is None:
        raise HTTPException(status_code=404, detail=f"No page {page_id}")

    slots = list(
        session.exec(
            select(PageTimeSlot)
            .where(PageTimeSlot.page_id == page_id)
            .order_by(PageTimeSlot.minute_of_day)  # type: ignore[arg-type]
        ).all()
    )
    if not slots:
        raise HTTPException(
            status_code=409,
            detail=(
                f"{page.name} has no publishing times configured. "
                "Add them on Settings."
            ),
        )
    if not page.metricool_blog_id:
        raise HTTPException(
            status_code=409,
            detail=f"{page.name} has no metricool_blog_id to check the planner with.",
        )

    zone = ZoneInfo(settings.timezone)
    now = datetime.now(zone).replace(tzinfo=None)

    try:
        rows = publisher.list_scheduled(
            page.metricool_blog_id, now, now + timedelta(days=SLOT_SEARCH_DAYS)
        )
    except publisher.PublishError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error

    # To the minute, so a post moved by hand a second off still counts as
    # occupying its slot.
    busy = set()
    for row in rows:
        stamp = (row.get("publicationDate") or {}).get("dateTime", "")
        try:
            busy.add(datetime.fromisoformat(stamp).replace(second=0, microsecond=0))
        except ValueError:
            # A row whose time we cannot read is not evidence that a slot is
            # free, but it is also not something to fail the whole search over.
            continue

    taken = 0
    for day in range(SLOT_SEARCH_DAYS):
        midnight = (now + timedelta(days=day)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        for slot in slots:
            when = midnight + timedelta(minutes=slot.minute_of_day)
            # `>` not `>=`: a slot at this exact minute is already in progress
            # as far as the planner is concerned, and Metricool refuses a
            # publication date in the past anyway.
            if when <= now:
                continue
            if when in busy:
                taken += 1
                continue
            return NextSlot(
                when=when.strftime("%Y-%m-%dT%H:%M:%S"), label=slot.label, taken=taken
            )

    raise HTTPException(
        status_code=409,
        detail=(
            f"Every slot for the next {SLOT_SEARCH_DAYS} days already has a post. "
            "Add another publishing time, or pick a time by hand."
        ),
    )


@router.get("/schedule")
def get_schedule(
    page_id: int = Query(1),
    days_back: int = Query(7, ge=0, le=90),
    days_ahead: int = Query(30, ge=1, le=90),
    session: Session = Depends(get_session),
) -> list[ScheduledPost]:
    """The planner window, newest first.

    Both directions by default: what went out this week is the other half of
    "what is scheduled", and during the cutover it is the half that shows the
    old system still working.
    """
    page = session.get(Page, page_id)
    if page is None:
        raise HTTPException(status_code=404, detail=f"No page {page_id}")
    if not page.metricool_blog_id:
        raise HTTPException(
            status_code=409,
            detail=f"{page.name} has no metricool_blog_id to read a schedule from.",
        )

    now = datetime.now()
    try:
        rows = publisher.list_scheduled(
            page.metricool_blog_id,
            now - timedelta(days=days_back),
            now + timedelta(days=days_ahead),
        )
    except publisher.PublishError as error:
        # 502, not 500: the planner is somebody else's service, and the screen
        # says so rather than pretending the schedule is empty.
        raise HTTPException(status_code=502, detail=str(error)) from error

    pushed = session.exec(
        select(Draft).where(Draft.metricool_post_id.is_not(None))  # type: ignore[union-attr]
    ).all()
    ours = {
        draft.metricool_post_id: draft.id
        for draft in pushed
        if draft.metricool_post_id and draft.id
    }

    posts = [_flatten(row, ours) for row in rows]
    posts.sort(key=lambda post: post.published_at, reverse=True)
    return posts
