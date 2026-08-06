"""Pages: list, read, edit.

One page in v1, so this is a small surface: the Settings screen reads a Page and
shows it. Prompts are files now and are edited in an editor, not here.

Nothing in the UI writes a Page any more — `daily_quota` was the only field it
edited, and it is gone. `PATCH` stays because `watermark_image_path` is still a
per-page value and Phase 4 is the code that reads it; a Page with the wrong
watermark needs a way back that is not a SQL prompt.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app.db import get_session
from app.models import Page

router = APIRouter(prefix="/pages", tags=["pages"])


class PageUpdate(BaseModel):
    """Every field optional — the Settings form sends only what changed.

    Identity is absent on purpose: `name`, `facebook_page_id` and
    `metricool_blog_id` come from Metricool and are not the operator's to edit.
    """

    watermark_image_path: str | None = None


@router.get("")
def list_pages(session: Session = Depends(get_session)) -> list[Page]:
    return list(session.exec(select(Page).order_by(Page.name)).all())


@router.get("/{page_id}")
def get_page(page_id: int, session: Session = Depends(get_session)) -> Page:
    page = session.get(Page, page_id)
    if page is None:
        raise HTTPException(status_code=404, detail=f"No page {page_id}")
    return page


@router.patch("/{page_id}")
def update_page(
    page_id: int,
    update: PageUpdate,
    session: Session = Depends(get_session),
) -> Page:
    page = session.get(Page, page_id)
    if page is None:
        raise HTTPException(status_code=404, detail=f"No page {page_id}")

    changes = update.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(page, field, value)
    page.updated_at = datetime.now(timezone.utc)

    session.add(page)
    session.commit()
    session.refresh(page)
    return page
