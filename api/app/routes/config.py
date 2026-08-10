"""The Composed Image layout: the file's defaults, and a Page's overrides.

`layout.yml` is parsed once at import into a frozen model and is still the
default. Serving it is what lets a screen show the values the compositor will
actually use, rather than a copy maintained by hand on the other side of the
wire — which is what the preview was doing, and which drifts the moment either
side is edited alone.

**It stopped being read-only.** The original note here said layout is config
rather than data, edited in a file and reviewed in a diff, for the same reason
the prompts are. That held while every Page rendered identically. It stopped
holding when the operator wanted a news card to look unlike a history card, and
a file cannot answer that: this API runs from a container image, so a written
file is gone at the next deploy.

So the file keeps the defaults — a change to it is still a diff — and a
`page_layout` row holds only what one Page changed. `DELETE` removes the row,
which is what makes "reset" mean *back to the file* rather than *back to
whatever the file said when you first pressed save*.

Image dimensions and the font stay out of it. 4:5 is the tallest ratio Facebook
renders in feed, and a font family that does not match the TTF's name table
makes resvg substitute a serif silently and still return a valid PNG — neither
failure is visible from a form.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session, select

from app import layout_for
from app.db import get_session
from app.models import Page, PageLayout
from app.settings import Layout

router = APIRouter(tags=["config"])


class LayoutOut(BaseModel):
    """The resolved layout, plus which fields this Page actually overrides.

    `overridden` is what lets the screen mark a changed field and offer a reset
    that means something. Derived from the row rather than by diffing against
    the defaults: a Page that deliberately sets a value *to* the current default
    has still overridden it, and would stop tracking the file if the file
    changed. Diffing would call that "unchanged" and be wrong in the one case
    the distinction exists for.
    """

    layout: Layout
    overridden: list[str]


def _page(session: Session, page_id: int | None) -> Page | None:
    if page_id is None:
        return None
    page = session.get(Page, page_id)
    if page is None:
        raise HTTPException(status_code=404, detail=f"No page {page_id}")
    return page


@router.get("/layout")
def get_layout(
    page_id: int | None = Query(None, description="Omit for the file's defaults"),
    session: Session = Depends(get_session),
) -> LayoutOut:
    _page(session, page_id)
    row = (
        session.exec(select(PageLayout).where(PageLayout.page_id == page_id)).first()
        if page_id is not None
        else None
    )
    return LayoutOut(
        layout=layout_for.resolve(session, page_id),
        overridden=sorted(
            name
            for name, value in (row.model_dump() if row else {}).items()
            if value is not None
            and name not in {"id", "page_id", "updated_at"}
        ),
    )


class LayoutPatch(BaseModel):
    """Only the fields being changed. `null` clears one back to the default.

    Distinguished from absent: `model_dump(exclude_unset=True)` is what makes
    "set this to null" and "do not touch this" different requests, which a
    per-field reset needs.
    """

    panel_ratio: float | None = None
    panel_max_ratio: float | None = None
    panel_color: str | None = None
    panel_opacity: float | None = None

    text_font_size_px: int | None = None
    text_line_height_ratio: float | None = None
    text_align: str | None = None
    text_color: str | None = None
    text_padding_left_px: int | None = None
    text_padding_right_px: int | None = None
    text_padding_top_px: int | None = None
    text_padding_bottom_px: int | None = None

    highlight_color: str | None = None

    watermark_max_px: int | None = None
    watermark_top_ratio: float | None = None

    portrait_size_px: int | None = None
    portrait_min_px: int | None = None
    portrait_max_width_ratio: float | None = None
    portrait_ring_pad_px: int | None = None
    portrait_border_width_px: int | None = None
    portrait_border_color: str | None = None


@router.patch("/layout")
def patch_layout(
    body: LayoutPatch,
    page_id: int = Query(...),
    session: Session = Depends(get_session),
) -> LayoutOut:
    """Change this Page's overrides. Validated by rendering the result."""
    _page(session, page_id)

    row = session.exec(
        select(PageLayout).where(PageLayout.page_id == page_id)
    ).first() or PageLayout(page_id=page_id)

    for name, value in body.model_dump(exclude_unset=True).items():
        setattr(row, name, value)

    # Validated before it is stored, by building the layout it would produce.
    # resvg does not fail on a bad value — it renders something wrong and
    # returns a valid PNG — so a 422 here is the only place this can be caught.
    try:
        Layout.model_validate(
            layout_for._merge(
                layout_for.defaults.model_dump(), layout_for.as_overrides(row)
            )
        )
    except Exception as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    session.add(row)
    session.commit()

    return get_layout(page_id=page_id, session=session)


@router.delete("/layout")
def reset_layout(
    page_id: int = Query(...),
    session: Session = Depends(get_session),
) -> LayoutOut:
    """Back to the file's defaults, by deleting the row rather than rewriting it.

    Deleting is what keeps the Page tracking `layout.yml` afterwards. Writing
    today's defaults back into the row would look identical and behave
    differently the next time the file changed.
    """
    _page(session, page_id)

    row = session.exec(select(PageLayout).where(PageLayout.page_id == page_id)).first()
    if row is not None:
        session.delete(row)
        session.commit()

    return get_layout(page_id=page_id, session=session)
