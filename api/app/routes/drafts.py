"""Generate a run, then read and edit what it produced.

`POST /generate` returns ids immediately and fills the rows in the background;
the client polls `GET /drafts/{id}` until `status` leaves `generating`. The row
is the job record, which is why progress lives on it.
"""

import io
from datetime import datetime, timezone

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    Query,
    UploadFile,
)
from PIL import Image
from pydantic import BaseModel
from sqlmodel import Session, select

from app import generate, media
from app.db import get_session
from app.models import Draft, DraftStatus, Page, SourceItemBase
from app.publish import metricool as publisher
from app.settings import layout
from app.writer import validators

router = APIRouter(tags=["drafts"])


class GenerateRequest(BaseModel):
    """Source Items **by value**, which is what makes generate the only write.

    The Cart holds items rather than row ids, so nothing is stored until a run
    uses it. `generate.resolve_sources` decides which kinds may be authored by
    the client and which must already exist.
    """

    page_ids: list[int]
    sources: list[SourceItemBase] = []
    topic: str | None = None


@router.post("/generate", status_code=202)
def start_generate(
    request: GenerateRequest,
    background: BackgroundTasks,
    session: Session = Depends(get_session),
) -> list[int]:
    """202: accepted, not finished. One real draft took ~130s."""
    try:
        draft_ids = generate.start_run(
            session, request.page_ids, request.sources, request.topic
        )
    except generate.GenerateError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    background.add_task(generate.run_drafts, draft_ids)
    return draft_ids


@router.get("/drafts")
def list_drafts(
    status: DraftStatus | None = Query(None),
    page_id: int | None = Query(None),
    session: Session = Depends(get_session),
) -> list[Draft]:
    query = select(Draft)
    if status is not None:
        query = query.where(Draft.status == status)
    if page_id is not None:
        query = query.where(Draft.page_id == page_id)
    return list(session.exec(query.order_by(Draft.created_at.desc())).all())  # type: ignore[union-attr]


@router.get("/drafts/{draft_id}")
def get_draft(draft_id: int, session: Session = Depends(get_session)) -> Draft:
    draft = session.get(Draft, draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail=f"No draft {draft_id}")
    return draft


class DraftEdit(BaseModel):
    """The written fields only. Status moves through its own routes.

    `image_prompt` is here because it is the only lever on a hero the model
    refused — the writer produced it, so the operator has to be able to correct
    it before paying for another generation.
    """

    hook: str | None = None
    caption: str | None = None
    first_comment: str | None = None
    highlight_phrases: list[str] | None = None
    hashtags: list[str] | None = None
    image_prompt: str | None = None
    inset_size_px: int | None = None
    inset_x_ratio: float | None = None
    inset_y_ratio: float | None = None


DRAWN_FIELDS = (
    "hook",
    "highlight_phrases",
    "inset_size_px",
    "inset_x_ratio",
    "inset_y_ratio",
)
"""The only edits that change the picture. Caption and body are not on it."""


@router.patch("/drafts/{draft_id}")
def update_draft(
    draft_id: int,
    edit: DraftEdit,
    session: Session = Depends(get_session),
) -> Draft:
    """Save, and redraw the composite if the saved text is on it.

    Recompositing used to be a button the operator pressed after saving, which
    made "the row" and "the picture" two things that could disagree — and they
    disagreed by default, because the obvious thing to do after editing is to
    save and move on. Doing it here means the stored PNG always matches the
    stored text, whatever client did the saving.

    Free, so there is nothing to weigh: the hero is reused and only the panel is
    redrawn. Buying a *new* hero stays an explicit request.
    """
    draft = _editable(session, draft_id)
    changes = edit.model_dump(exclude_unset=True)
    redraw = any(
        field in changes and changes[field] != getattr(draft, field)
        for field in DRAWN_FIELDS
    )

    if "hashtags" in changes:
        # The box is free text split on spaces, so this path never sees the
        # model's schema. Same rule, applied where the edit lands.
        changes["hashtags"] = validators.normalise_hashtags(changes["hashtags"])

    # Clamped where the edit lands, not only where it is drawn: the row is read
    # back into a slider and a drag handle, and a value they would never render
    # is a control that lies about what it is set to.
    if changes.get("inset_size_px") is not None:
        changes["inset_size_px"] = layout.portrait.clamp(
            changes["inset_size_px"], layout.image.width
        )
    for axis in ("inset_x_ratio", "inset_y_ratio"):
        # 0-1 of the card, as the old app stored it. Off the edge is allowed
        # right up to it: half a disc hanging off the corner is a legitimate
        # crop, and the old editor clamped to exactly this.
        if changes.get(axis) is not None:
            changes[axis] = min(1.0, max(0.0, changes[axis]))

    for field, value in changes.items():
        setattr(draft, field, value)

    if redraw and draft.hero_image_path:
        page = session.get(Page, draft.page_id)
        if page is not None:
            fresh = generate.build_image(session, draft, page)
            kept = [w for w in draft.warnings if not w.startswith(generate.IMAGE_WARNING)]
            draft.warnings = kept + fresh

    return _save(session, draft)


@router.post("/drafts/{draft_id}/image")
def rebuild_image(
    draft_id: int,
    new_hero: bool = Query(
        False,
        description="Buy a new hero. Off by default because it is the one paid step.",
    ),
    session: Session = Depends(get_session),
) -> Draft:
    """Buy a new hero, or rebuild a composite that failed.

    `new_hero=true` discards the picture and pays for another. It is the only
    call in the app that spends money on demand, which is why it is a flag
    rather than the default.

    The default — reuse the hero, redraw the panel — is what `PATCH` now does on
    every save that touches the drawn text, so nothing in the UI calls it. It
    stays because a composite can fail on its own (a watermark that will not
    load), and the way back from that must not be to edit something you did not
    want to change.

    Synchronous, unlike `/generate`: re-compositing is milliseconds, and a new
    hero is a single call the operator is waiting on anyway.
    """
    draft = _editable(session, draft_id)
    page = session.get(Page, draft.page_id)
    if page is None:
        raise HTTPException(status_code=404, detail=f"No page {draft.page_id}")

    if new_hero:
        draft.hero_image_path = None

    # Rebound rather than appended: `warnings` is a plain JSON column, so an
    # in-place edit does not mark the row dirty and never persists.
    fresh = generate.build_image(session, draft, page)
    kept = [w for w in draft.warnings if not w.startswith(generate.IMAGE_WARNING)]
    draft.warnings = kept + fresh
    return _save(session, draft)


MAX_INSET_BYTES = 8 * 1024 * 1024
"""A phone photograph is 3-5MB. Bounded because the body is read into memory."""


@router.post("/drafts/{draft_id}/inset")
async def upload_inset(
    draft_id: int,
    file: UploadFile = File(description="Any image. Cropped to a circle when drawn."),
    session: Session = Depends(get_session),
) -> Draft:
    """Put a picture in the circle, and redraw the card around it.

    The one image in the app that comes from a person rather than a model, and
    the only reason the inset exists at all: the old app offered Upload beside
    Generate and defaulted to Upload (`circular-inset-dialog.tsx`).

    Re-encoded to PNG rather than stored as sent. The upload decides nothing
    about how it is drawn — the compositor cover-crops it to a disc at the
    draft's size — so keeping the original container buys nothing and keeps
    whatever the camera attached to it. Decoding here also means a file that is
    not an image is a 422 on the upload rather than a broken composite later.
    """
    draft = _editable(session, draft_id)
    page = session.get(Page, draft.page_id)
    if page is None:
        raise HTTPException(status_code=404, detail=f"No page {draft.page_id}")

    data = await file.read(MAX_INSET_BYTES + 1)
    if len(data) > MAX_INSET_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"That image is over {MAX_INSET_BYTES // (1024 * 1024)}MB.",
        )

    try:
        picture = Image.open(io.BytesIO(data))
        picture.load()
    except Exception as error:  # noqa: BLE001 — any decode failure is the same answer
        raise HTTPException(
            status_code=422, detail=f"That file is not an image Pillow can read ({error})."
        ) from error

    buffer = io.BytesIO()
    picture.convert("RGB").save(buffer, format="PNG")
    draft.inset_image_path = media.store.save(
        buffer.getvalue(), media.filename(draft_id, "inset", "png")
    )
    return _redrawn(session, draft, page)


@router.delete("/drafts/{draft_id}/inset")
def remove_inset(draft_id: int, session: Session = Depends(get_session)) -> Draft:
    """Take the circle off. Returns the draft, not 204, because the card changed.

    Size and position go with it, so the next upload starts on the seam at the
    default diameter rather than inheriting geometry chosen for a picture that
    is no longer there. Replacing keeps them, which is the point of Replace.

    The file is left on disk: an approved composite may already have been drawn
    with it, and the row that points at that composite has no way to say which
    inset went into it. Deleting the draft still takes it.
    """
    draft = _editable(session, draft_id)
    page = session.get(Page, draft.page_id)
    if page is None:
        raise HTTPException(status_code=404, detail=f"No page {draft.page_id}")

    draft.inset_image_path = None
    draft.inset_size_px = None
    draft.inset_x_ratio = None
    draft.inset_y_ratio = None
    return _redrawn(session, draft, page)


def _redrawn(session: Session, draft: Draft, page: Page) -> Draft:
    """Save, and rebuild the composite around whatever the inset now is.

    Free — the hero is reused and only the panel and the disc are redrawn — so
    there is nothing to weigh and no button to press. Same rule as `PATCH`:
    the stored PNG always matches the stored row.
    """
    if draft.hero_image_path:
        fresh = generate.build_image(session, draft, page)
        kept = [w for w in draft.warnings if not w.startswith(generate.IMAGE_WARNING)]
        draft.warnings = kept + fresh
    return _save(session, draft)


@router.delete("/drafts/{draft_id}", status_code=204)
def delete_draft(draft_id: int, session: Session = Depends(get_session)) -> None:
    """Gone for good, along with its pictures.

    Distinct from Reject, which is a decision that stays on the record and can
    be undone. This is for a row nobody should have to look at again — a failed
    run, a duplicate, a test.

    The files go too. They are named after the draft and nothing else points at
    them, so keeping them would leave the bucket growing with pictures no row
    can reach. A missing file is not an error here: the row may never have got
    one.

    A published draft cannot be deleted, and that is `_editable` rather than a
    rule about tidiness: Metricool holds a link to this draft's composite and
    Facebook has not fetched it yet. Deleting the row would take the picture
    with it and the post would go out blank.
    """
    draft = _editable(session, draft_id)

    for stored in (
        draft.hero_image_path,
        draft.composed_image_path,
        draft.inset_image_path,
    ):
        if stored:
            media.store.delete(stored)

    session.delete(draft)
    session.commit()


class PublishRequest(BaseModel):
    when: datetime | None = None
    """Local time to publish. `None` means as soon as Metricool will take it."""


@router.post("/drafts/{draft_id}/publish")
def publish_draft(
    draft_id: int,
    request: PublishRequest | None = None,
    session: Session = Depends(get_session),
) -> Draft:
    """Hand Metricool the post and the link to its picture, record what it is called.

    Separate from Approve, and it stays separate. Approve is a queue movement
    with an undo — `unapprove` exists and the toast offers it. This is the step
    that cannot be taken back, so it is its own button and its own decision.

    There is no upload step any more, and its disappearance is the whole reason
    the freeze exists. Metricool stores a *link*; Facebook fetches it when the
    post is due, days later. That used to mean the composite had to be copied to
    a name a rebuild could never touch, because the live composite is renamed on
    every edit and the old one is deleted. Freezing a published draft
    (`_editable`) makes the live composite permanent instead, so the copy became
    a second file that only existed to be identical to the first.

    Publishing twice is refused rather than allowed to make a duplicate — the
    id is on the row, and the planner is where a scheduled post is changed
    (ADR-0001).
    """
    draft = _require(session, draft_id)

    if draft.metricool_post_id:
        raise HTTPException(
            status_code=409,
            detail=(
                f"That draft is already in Metricool as post "
                f"{draft.metricool_post_id}. Change it there."
            ),
        )
    if draft.status == DraftStatus.FAILED:
        raise HTTPException(
            status_code=409, detail="That draft failed and has nothing to publish."
        )
    if not draft.composed_image_path:
        raise HTTPException(
            status_code=409,
            detail="That draft has no composed image, so there is nothing to post.",
        )

    page = session.get(Page, draft.page_id)
    if page is None:
        raise HTTPException(status_code=404, detail=f"No page {draft.page_id}")
    if not page.metricool_blog_id:
        raise HTTPException(
            status_code=409,
            detail=f"{page.name} has no metricool_blog_id to publish against.",
        )

    # The composite is already a JPEG in a public bucket, so there is nothing to
    # upload — this is the link to the file `build_image` wrote. It used to be
    # copied to a stable `{draft_id}.jpg` first, on the reasoning that a rebuild
    # would otherwise move the picture out from under a scheduled post. The
    # freeze in `_editable` is what removed the need: a published draft cannot
    # rebuild, so the composite it points at can no longer change or be deleted.
    url = media.public_url(draft.composed_image_path)

    try:
        normalized = publisher.normalize_image(url, page.metricool_blog_id)
        post_id = publisher.schedule(
            page.metricool_blog_id,
            _post_text(draft),
            draft.first_comment,
            normalized,
            request.when if request else None,
        )
    except publisher.PublishError as error:
        # 502: the failure is upstream, and the draft is untouched and still
        # publishable once whatever broke is fixed.
        raise HTTPException(status_code=502, detail=str(error)) from error

    draft.metricool_post_id = post_id or "queued"
    return _save(session, draft)


def _post_text(draft: Draft) -> str:
    """The caption and its hashtags, which is what Facebook shows.

    The hook is not here: it is drawn *on the image*, and repeating it as the
    caption prints the same sentence twice on one post. The first comment goes
    to Metricool separately, as `firstCommentText`.
    """
    caption = (draft.caption or "").strip()
    tags = " ".join(draft.hashtags)
    return f"{caption}\n\n{tags}".strip() if tags else caption


@router.post("/drafts/{draft_id}/approve")
def approve_draft(draft_id: int, session: Session = Depends(get_session)) -> Draft:
    """A failed run cannot be approved — there is nothing in it to approve.

    Rejecting one is still allowed: that is how it leaves the queue.
    """
    if _require(session, draft_id).status == DraftStatus.FAILED:
        raise HTTPException(
            status_code=409, detail="That draft failed and has nothing to approve."
        )
    return _set_status(session, draft_id, DraftStatus.APPROVED)


@router.post("/drafts/{draft_id}/unapprove")
def unapprove_draft(draft_id: int, session: Session = Depends(get_session)) -> Draft:
    """Nothing publishes in v1, so Approve is a queue movement, not a commitment.

    An approved Draft can come back, which is why nothing downstream may treat
    Approve as final.
    """
    return _set_status(session, draft_id, DraftStatus.REVIEW)


@router.post("/drafts/{draft_id}/reject")
def reject_draft(draft_id: int, session: Session = Depends(get_session)) -> Draft:
    return _set_status(session, draft_id, DraftStatus.REJECTED)


def _require(session: Session, draft_id: int) -> Draft:
    draft = session.get(Draft, draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail=f"No draft {draft_id}")
    if draft.status == DraftStatus.GENERATING:
        raise HTTPException(
            status_code=409, detail="That draft is still being written."
        )
    return draft


def _editable(session: Session, draft_id: int) -> Draft:
    """`_require`, plus: a draft that has been pushed to Metricool is frozen.

    ADR-0001 already says the planner is where a scheduled post is changed, but
    nothing enforced it — `metricool_post_id` was read in exactly one place, the
    refusal to publish twice. So editing a published draft was allowed and did
    nothing useful: the row changed here while the post Metricool would send
    stayed as it was.

    It is now also a correctness rule about *storage*, which is why it is a
    helper rather than a note in a docstring. Metricool holds a link to the
    composite and Facebook fetches it when the post is due, days later. Every
    edit that redraws writes a new composite and deletes the one it supersedes
    — so an edit here would delete the picture out from under a scheduled post,
    which then goes out with nothing. Freezing the draft is what makes that
    deletion safe, and is why publishing no longer needs its own copy of the
    file.

    Status routes are deliberately not covered: approve and reject move a row
    through a queue and never touch a picture.
    """
    draft = _require(session, draft_id)
    if draft.metricool_post_id:
        raise HTTPException(
            status_code=409,
            detail=(
                f"That draft is in Metricool as post {draft.metricool_post_id}. "
                "Change it in the planner — editing it here would not change "
                "what goes out, and would break the image the post points at."
            ),
        )
    return draft


def _set_status(session: Session, draft_id: int, status: DraftStatus) -> Draft:
    draft = _require(session, draft_id)
    draft.status = status
    return _save(session, draft)


def _save(session: Session, draft: Draft) -> Draft:
    draft.updated_at = datetime.now(timezone.utc)
    session.add(draft)
    session.commit()
    session.refresh(draft)
    return draft
