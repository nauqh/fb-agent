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

import base64

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlmodel import Session, col, select

from app import layout_for, media
from app.db import get_session
from app.image import compositor
from app.image import text as overlay
from app.models import Draft, Page, PageLayout
from app.settings import Align, Layout, Template

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


NOT_OVERRIDES = frozenset({"id", "page_id", "updated_at"})
"""Columns of `page_layout` that are not one of the layout's values."""


def _layout_with(session: Session, page_id: int, changes: dict) -> Layout:
    """This Page's layout, with `changes`' flat column values laid over it.

    The shape both the write and the preview need: `{**yaml, **row, **changes}`.
    `changes` is a `LayoutPatch` dumped with `exclude_unset=True`, so a field
    that is present and `null` clears an override and one that is absent leaves
    it alone — the distinction a per-field reset is built on.

    The transient `PageLayout` is never added to the session. It exists because
    `as_overrides` is the one place the flat column names and the nested file
    shape are related, and a second mapping here would be the copy that drifts.
    """
    row = session.exec(select(PageLayout).where(PageLayout.page_id == page_id)).first()
    flat = {
        name: value
        for name, value in (row.model_dump() if row else {}).items()
        if name not in NOT_OVERRIDES
    }
    flat.update(changes)

    return Layout.model_validate(
        layout_for._merge(
            layout_for.defaults.model_dump(),
            layout_for.as_overrides(PageLayout(page_id=page_id, **flat)),
        )
    )


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
            if value is not None and name not in NOT_OVERRIDES
        ),
    )


class LayoutPatch(BaseModel):
    """Only the fields being changed. `null` clears one back to the default.

    Distinguished from absent: `model_dump(exclude_unset=True)` is what makes
    "set this to null" and "do not touch this" different requests, which a
    per-field reset needs.
    """

    template: Template | None = None

    panel_ratio: float | None = None
    panel_max_ratio: float | None = None
    panel_color: str | None = None
    panel_opacity: float | None = None

    text_font_size_px: int | None = None
    text_line_height_ratio: float | None = None
    text_align: Align | None = None
    text_color: str | None = None
    text_uppercase: bool | None = None
    text_padding_left_px: int | None = None
    text_padding_right_px: int | None = None
    text_padding_top_px: int | None = None
    text_padding_bottom_px: int | None = None

    highlight_color: str | None = None

    watermark_max_px: int | None = None
    watermark_top_ratio: float | None = None

    badge_color: str | None = None
    badge_font_size_px: int | None = None

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
    changes = body.model_dump(exclude_unset=True)

    # Validated before it is stored, by building the layout it would produce.
    # resvg does not fail on a bad value — it renders something wrong and
    # returns a valid PNG — so a 422 here is the only place this can be caught.
    try:
        _layout_with(session, page_id, changes)
    except Exception as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    row = session.exec(
        select(PageLayout).where(PageLayout.page_id == page_id)
    ).first() or PageLayout(page_id=page_id)
    for name, value in changes.items():
        setattr(row, name, value)

    session.add(row)
    session.commit()

    return get_layout(page_id=page_id, session=session)


class LayoutSample(BaseModel):
    """What to draw the sample card from: unsaved edits, and text to put in them."""

    text: str = Field(min_length=1, description="The hook to wrap into the panel")
    highlight_phrases: list[str] = []
    patch: LayoutPatch = LayoutPatch()
    draft_id: int | None = Field(
        None, description="Whose hero to draw on. The Page's newest, by default"
    )


class SampleOut(BaseModel):
    """The card, plus the numbers the browser preview cannot know it got wrong."""

    image_base64: str
    content_type: str = "image/jpeg"
    hero_draft_id: int
    """Which draft's hero this was drawn on — the sample is not a fixed picture."""

    lines: list[str]
    panel_height_px: int


@router.post("/layout/sample")
def render_sample(
    body: LayoutSample,
    page_id: int = Query(...),
    session: Session = Depends(get_session),
) -> SampleOut:
    """One card, drawn by the compositor, from values that are not saved yet.

    The editor's live preview is CSS and is an approximation on purpose — it
    moves as a slider does. This is the other half: the same `text.plan` and
    `compositor.compose` that publish, so the wrap, the kerning and the panel
    height are the real ones rather than the browser's guess at them. Both are
    needed. A preview that only updates after a round trip is not a preview, and
    an approximation is not proof of the pixels.

    **Drawn on an existing draft's hero, never a fresh one.** `hero.generate` is
    the one call in this app that bills per invocation, and a preview button
    that spends money is a preview button nobody presses twice.

    Nothing is written: the layout is resolved through the same merge the write
    path validates with, and the JPEG is returned rather than stored.
    """
    page = _page(session, page_id)

    heroed = select(Draft).where(
        Draft.page_id == page_id, col(Draft.hero_image_path).is_not(None)
    )
    if body.draft_id is not None:
        heroed = heroed.where(Draft.id == body.draft_id)
    draft = session.exec(heroed.order_by(col(Draft.id).desc())).first()
    if draft is None or not draft.hero_image_path:
        raise HTTPException(
            status_code=409,
            detail=(
                "No draft on this Page has a hero image to sample. Generate one "
                "on the queue first — a preview does not draw its own, because "
                "that is a paid call per press."
            ),
        )

    try:
        layout = _layout_with(session, page_id, body.patch.model_dump(exclude_unset=True))
    except Exception as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    plan = overlay.plan(body.text, layout)
    mark, mark_text = page.watermark() if page else (None, None)
    try:
        # No inset: the circle is a property of one draft, not of the layout
        # being edited, and a borrowed hero's portrait would be a stranger's
        # face on a card about type sizes.
        jpeg = compositor.compose(
            media.store.read(draft.hero_image_path),
            plan,
            body.highlight_phrases,
            mark,
            None,
            layout,
            fallback_text=mark_text,
            badge_text=page.badge_text if page else None,
        )
    except compositor.CompositeError as error:
        # The clipped-panel and unreadable-watermark cases both land here. They
        # are exactly what an operator is about to save, so they are a 422 with
        # the compositor's own sentence, not a 500.
        raise HTTPException(status_code=422, detail=str(error)) from error

    return SampleOut(
        image_base64=base64.b64encode(jpeg).decode(),
        hero_draft_id=draft.id or 0,
        lines=plan.lines,
        panel_height_px=plan.panel_height_px,
    )


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
