"""Pages: list, read, edit.

One page in v1, so this is a small surface: the Settings screen reads a Page and
shows it. Prompts are files now and are edited in an editor, not here.

Nothing in the UI writes a Page any more — `daily_quota` was the only field it
edited, and it is gone. `PATCH` stays because `watermark_image_path` is still a
per-page value and Phase 4 is the code that reads it; a Page with the wrong
watermark needs a way back that is not a SQL prompt.
"""

import io
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from PIL import Image
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app import media
from app.db import get_session
from app.models import Page, PageTimeSlot

router = APIRouter(prefix="/pages", tags=["pages"])


class PageUpdate(BaseModel):
    """Every field optional — the Settings form sends only what changed.

    Identity is absent on purpose: `name`, `facebook_page_id` and
    `metricool_blog_id` come from Metricool and are not the operator's to edit.
    """

    watermark_image_path: str | None = None
    watermark_text: str | None = None
    """Null here means "print the Page's name" — it is a clear, not a blank."""

    watermark_enabled: bool | None = None
    """False publishes a clean photograph: no image mark and no text either."""

    badge_text: str | None = None
    """The headline chip's word. Null draws no chip. `full_overlay` only."""


@router.get("")
def list_pages(session: Session = Depends(get_session)) -> list[Page]:
    return list(session.exec(select(Page).order_by(Page.name)).all())


@router.get("/{page_id}")
def get_page(page_id: int, session: Session = Depends(get_session)) -> Page:
    page = session.get(Page, page_id)
    if page is None:
        raise HTTPException(status_code=404, detail=f"No page {page_id}")
    return page


def _page(session: Session, page_id: int) -> Page:
    page = session.get(Page, page_id)
    if page is None:
        raise HTTPException(status_code=404, detail=f"No page {page_id}")
    return page


MAX_WATERMARK_BYTES = 4 * 1024 * 1024
"""A wordmark is tens of kilobytes. The cap is for what is not a wordmark."""


@router.post("/{page_id}/watermark")
async def upload_watermark(
    page_id: int,
    file: UploadFile = File(description="The page's logo. Transparent PNG, ideally."),
    session: Session = Depends(get_session),
) -> Page:
    """Give this Page a mark without committing a file to the repo.

    Eight of the ten Pages have no committed asset and so publish with nothing
    stamped on them at all. Their artwork is not in git and their operator
    cannot put it there, which made "commit a PNG under `api/assets/`" a rule
    only two Pages could follow.

    Hosting the watermark is the exact thing that failed in the old system — the
    bucket was cleared and every path started returning `NoSuchKey`. What made
    that eight silent months rather than one failed post was the compositor
    swallowing it (`return null`, image-composite.ts:136) and printing the page
    name instead. Ours raises (`compositor._watermark`), so the same accident is
    a draft that fails with the file named in `draft.error`. That is what makes
    hosting safe here and did not there.

    Re-encoded to PNG **with its alpha kept**. The mark is white ink meant to sit
    on a photograph; flattened to RGB it arrives as a white wordmark on a white
    box, which is not a subtle failure but is an easy one to write —
    `upload_inset` does exactly that, correctly, because a disc is cover-cropped
    over the panel and has no transparency to lose.
    """
    page = _page(session, page_id)

    data = await file.read(MAX_WATERMARK_BYTES + 1)
    if len(data) > MAX_WATERMARK_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"That image is over {MAX_WATERMARK_BYTES // (1024 * 1024)}MB.",
        )

    try:
        picture = Image.open(io.BytesIO(data))
        picture.load()
    except Exception as error:  # noqa: BLE001 — any decode failure is the same answer
        raise HTTPException(
            status_code=422,
            detail=f"That file is not an image Pillow can read ({error}).",
        ) from error

    buffer = io.BytesIO()
    picture.convert("RGBA").save(buffer, format="PNG")

    superseded = page.watermark_upload_path
    page.watermark_upload_path = media.store.save(
        buffer.getvalue(), media.filename(page_id, "page-watermark", "png")
    )
    page.updated_at = datetime.now(timezone.utc)
    session.add(page)
    session.commit()
    session.refresh(page)

    # Only after the row points at the replacement, and unlike a composite this
    # is safe to drop at all: the mark is drawn *into* the JPEG, so a published
    # card keeps its pixels when the source object goes.
    if superseded and superseded != page.watermark_upload_path:
        media.store.delete(superseded)

    return page


@router.delete("/{page_id}/watermark")
def remove_watermark(page_id: int, session: Session = Depends(get_session)) -> Page:
    """Drop the upload. The Page falls back to its committed asset, or to none.

    Returns the Page rather than 204 because what it renders with has changed,
    and the screen has to show which of the two sources is now in force.
    """
    page = _page(session, page_id)

    dropped = page.watermark_upload_path
    page.watermark_upload_path = None
    page.updated_at = datetime.now(timezone.utc)
    session.add(page)
    session.commit()
    session.refresh(page)

    if dropped:
        media.store.delete(dropped)
    return page


@router.patch("/{page_id}")
def update_page(
    page_id: int,
    update: PageUpdate,
    session: Session = Depends(get_session),
) -> Page:
    page = _page(session, page_id)

    changes = update.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(page, field, value)
    page.updated_at = datetime.now(timezone.utc)

    session.add(page)
    session.commit()
    session.refresh(page)
    return page


# --- publishing times ---------------------------------------------------------
#
# The Page's standing decision about when it posts. Policy, not schedule state:
# see `PageTimeSlot` for why this does not reverse ADR-0001.


class TimeSlotIn(BaseModel):
    """A time of day, as a form sends it."""

    hour: int = Field(ge=0, le=23)
    minute: int = Field(ge=0, le=59)


@router.get("/{page_id}/slots")
def list_slots(page_id: int, session: Session = Depends(get_session)) -> list[PageTimeSlot]:
    """This Page's publishing times, earliest first."""
    _page(session, page_id)
    return list(
        session.exec(
            select(PageTimeSlot)
            .where(PageTimeSlot.page_id == page_id)
            .order_by(PageTimeSlot.minute_of_day)  # type: ignore[arg-type]
        ).all()
    )


@router.post("/{page_id}/slots", status_code=201)
def add_slot(
    page_id: int,
    slot: TimeSlotIn,
    session: Session = Depends(get_session),
) -> PageTimeSlot:
    """Add a time. The same time twice is refused rather than stored.

    A duplicate is not two slots — it is one counted twice, and "next available"
    would offer it, find it taken and offer it again on the next pass.
    """
    _page(session, page_id)
    minute = slot.hour * 60 + slot.minute

    existing = session.exec(
        select(PageTimeSlot)
        .where(PageTimeSlot.page_id == page_id)
        .where(PageTimeSlot.minute_of_day == minute)
    ).first()
    if existing is not None:
        raise HTTPException(
            status_code=409, detail=f"{existing.label} is already a slot for this Page."
        )

    row = PageTimeSlot(page_id=page_id, minute_of_day=minute)
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


@router.delete("/{page_id}/slots/{slot_id}", status_code=204)
def remove_slot(
    page_id: int, slot_id: int, session: Session = Depends(get_session)
) -> None:
    """Removing a slot changes tomorrow's suggestion and nothing already queued.

    Nothing points at a slot — a scheduled post carries its own time in
    Metricool's planner — so this cannot cascade into published work.
    """
    row = session.get(PageTimeSlot, slot_id)
    if row is None or row.page_id != page_id:
        raise HTTPException(status_code=404, detail=f"No slot {slot_id} on page {page_id}")
    session.delete(row)
    session.commit()
