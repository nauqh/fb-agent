"""Which Competitors feed which Pages.

The assignment only. The competitor *list* stays Metricool's and is still never
stored (`CONTEXT.md`) — `GET /sources/competitors/pages` reads it live. What is
stored here is a decision Metricool has no way to express: one competitor
serving several of your Pages.

Why it has to exist is a limit, not a preference. A Metricool account may
configure 100 competitors **in total**. Five Pages that should each watch the
same twenty sources would need those twenty added five times, spending the whole
allowance on twenty distinct sources. So a competitor is added once, under
whichever Page has room, and assigned here to every Page that should read it.

Until a Page has any assignment it falls back to the competitor set it owns in
Metricool — see `routes/sources._visible_to`, which is where that rule lives.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app.db import get_session
from app.models import Page, PageCompetitor
from app.sources import metricool

router = APIRouter(prefix="/competitors", tags=["competitors"])


class AssignmentIn(BaseModel):
    """The complete set for a Page. Sent whole, not as add/remove.

    A checkbox list is a set, and sending the set is what makes the request
    idempotent: two clicks racing each other end at the state the second one
    described, rather than at whichever order the deltas happened to arrive in.
    """

    competitor_page_ids: list[str]
    names: dict[str, str] = {}
    """Display names by id, for showing an assignment Metricool no longer lists.
    Optional — a missing name renders as the id, which is ugly but not wrong."""

    notes: dict[str, str] = {}
    """Why this Page reads each competitor, by id. Optional.

    A table has no `git log`, and keeping this mapping in a config file — which
    would have had one — was rejected because it would put the change behind a
    deploy. This is where the reasoning goes instead. An id absent from here
    keeps whatever note it already had rather than losing it, so sending a bare
    set of ids cannot silently erase them.
    """


@router.get("/assignments")
def get_assignments(
    page_id: int,
    session: Session = Depends(get_session),
) -> list[PageCompetitor]:
    if session.get(Page, page_id) is None:
        raise HTTPException(status_code=404, detail=f"No page {page_id}")
    return list(
        session.exec(
            select(PageCompetitor).where(PageCompetitor.page_id == page_id)
        ).all()
    )


@router.put("/assignments")
def set_assignments(
    page_id: int,
    body: AssignmentIn,
    session: Session = Depends(get_session),
) -> list[PageCompetitor]:
    """Replace this Page's assignments with the set given.

    Replace rather than merge, for the reason `AssignmentIn` gives. Removing the
    last one puts the Page back on the Metricool-set fallback, which is a real
    state and not an error: it is what every Page starts in.
    """
    if session.get(Page, page_id) is None:
        raise HTTPException(status_code=404, detail=f"No page {page_id}")

    wanted = {value.strip() for value in body.competitor_page_ids if value.strip()}
    existing = {
        row.competitor_page_id: row
        for row in session.exec(
            select(PageCompetitor).where(PageCompetitor.page_id == page_id)
        ).all()
    }

    for competitor_page_id, row in existing.items():
        if competitor_page_id not in wanted:
            session.delete(row)
            continue
        # Kept rows take an updated note, and keep the one they had when none is
        # sent. A screen that submits the tick list without the notes must not
        # wipe the reasoning as a side effect.
        if competitor_page_id in body.notes:
            row.note = body.notes[competitor_page_id].strip() or None
            session.add(row)

    for competitor_page_id in wanted - existing.keys():
        session.add(
            PageCompetitor(
                page_id=page_id,
                competitor_page_id=competitor_page_id,
                name=body.names.get(competitor_page_id),
                note=(body.notes.get(competitor_page_id) or "").strip() or None,
            )
        )

    session.commit()
    return list(
        session.exec(
            select(PageCompetitor).where(PageCompetitor.page_id == page_id)
        ).all()
    )


class PoolEntryIn(BaseModel):
    """A Facebook page to start watching."""

    page_id: int
    """Which Metricool profile to add it under.

    Only decides where the allowance is spent, not who may read it — any Page can
    be assigned the result. It has to be named because Metricool's competitor
    sets belong to a profile; there is no account-level list to add to.
    """

    facebook_page_id: str
    """The numeric page id, which is what Metricool's `id` parameter takes."""


@router.post("", status_code=201)
def add_to_pool(
    body: PoolEntryIn,
    session: Session = Depends(get_session),
) -> dict:
    """Add a competitor to Metricool's set for a profile.

    Writes to Metricool rather than storing anything here: their list stays the
    one that exists, and this drives it. Nothing about the competitor is kept
    locally — `GET /sources/competitors/pages` re-reads it live.

    The account ceiling is 100 competitors in total. Metricool enforces it and
    the error is passed through, since a limit refusal is exactly the thing an
    operator needs to read verbatim.
    """
    page = session.get(Page, body.page_id)
    if page is None:
        raise HTTPException(status_code=404, detail=f"No page {body.page_id}")

    facebook_page_id = body.facebook_page_id.strip()
    if not facebook_page_id.isdigit():
        # Their API takes the numeric id. A pasted profile URL or @handle fails
        # upstream with an unhelpful 500, so it is refused here with a sentence.
        raise HTTPException(
            status_code=422,
            detail=(
                "That needs to be the numeric Facebook page id — the digits, not "
                "a URL or an @name."
            ),
        )

    try:
        metricool.add_competitor(page, facebook_page_id)
    except metricool.MetricoolError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error

    return {"added": facebook_page_id, "page_id": body.page_id}


@router.delete("/{competitor_id}", status_code=204)
def remove_from_pool(
    competitor_id: int,
    page_id: int,
    session: Session = Depends(get_session),
) -> None:
    """Stop watching a competitor. `competitor_id` is Metricool's row id.

    Assignments naming it are left alone rather than cleaned up. They match no
    posts once the competitor is gone, and deleting them would silently discard
    the operator's decision — re-adding the same page should bring it back, not
    require re-ticking every Page.
    """
    page = session.get(Page, page_id)
    if page is None:
        raise HTTPException(status_code=404, detail=f"No page {page_id}")

    try:
        metricool.remove_competitor(page, competitor_id)
    except metricool.MetricoolError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


class ProfileUsageOut(BaseModel):
    blog_id: str
    label: str
    competitors: int
    managed: bool


class AllowanceOut(BaseModel):
    """How much of Metricool's competitor limit is spent, account-wide."""

    used: int
    limit: int
    remaining: int
    profiles: list[ProfileUsageOut]


@router.get("/allowance")
def get_allowance(session: Session = Depends(get_session)) -> AllowanceOut:
    """The competitor budget, across **every** profile on the Metricool account.

    Not just the ones with a Page here, and that is the point. Measured while
    this was written: 92 of 100 in use, 44 of them on profiles this app does not
    manage. An operator counting only what this app shows would have believed
    they had 52 slots free when they had 8 — and the failure mode is discovering
    it as a refusal on the add form.

    Costs one request per profile, so it is deliberately a separate call rather
    than part of the competitor list: a screen that shows the list should not
    wait several seconds for a number beside it.
    """
    managed = {
        page.metricool_blog_id
        for page in session.exec(select(Page)).all()
        if page.metricool_blog_id
    }

    try:
        allowance = metricool.fetch_allowance(managed)
    except metricool.MetricoolError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error

    return AllowanceOut(
        used=allowance.used,
        limit=allowance.limit,
        remaining=allowance.remaining,
        profiles=[
            ProfileUsageOut(
                blog_id=one.blog_id,
                label=one.label,
                competitors=one.competitors,
                managed=one.managed,
            )
            for one in allowance.profiles
        ],
    )
