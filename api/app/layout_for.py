"""One Page's Composed Image layout: the file's defaults, plus its overrides.

`config/layout.yml` is the default and stays in git, where a change to it is a
diff. A `page_layout` row holds only what one Page changed, and resolution is
`{**yaml, **row}` field by field — so a value nobody has touched keeps tracking
the file, and resetting a Page is deleting its row rather than writing the
current defaults back into it.

That direction matters. Seeding a row with today's values would look identical
and behave differently the first time `layout.yml` changed: every Page would
silently keep the old number, and the file would stop being the default it
claims to be.
"""

from sqlmodel import Session, select

from app.models import PageLayout
from app.settings import Layout
from app.settings import layout as defaults

__all__ = ["as_overrides", "defaults", "resolve", "resolve_draft"]


def _merge(base: dict, override: dict) -> dict:
    """`override`'s non-null values win. Recurses into the nested blocks."""
    merged = dict(base)
    for key, value in override.items():
        if value is None:
            continue
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def as_overrides(row: PageLayout | None) -> dict:
    """A `page_layout` row in the shape of `layout.yml`, nulls included.

    The flat column names exist because a nullable float is a column and a
    nullable nested object is not — `panel.opacity` has to be storable on its
    own, without `panel.color` coming with it. This is the one place the two
    shapes are related, so a column added to the model has exactly one other
    line to change.
    """
    if row is None:
        return {}
    return {
        "template": row.template,
        "panel": {
            "ratio": row.panel_ratio,
            "max_ratio": row.panel_max_ratio,
            "color": row.panel_color,
            "opacity": row.panel_opacity,
        },
        "text": {
            "font_size_px": row.text_font_size_px,
            "line_height_ratio": row.text_line_height_ratio,
            "align": row.text_align,
            "color": row.text_color,
            "uppercase": row.text_uppercase,
            "padding": {
                "left_px": row.text_padding_left_px,
                "right_px": row.text_padding_right_px,
                "top_px": row.text_padding_top_px,
                "bottom_px": row.text_padding_bottom_px,
            },
        },
        "highlight": {"color": row.highlight_color},
        "watermark": {
            "max_px": row.watermark_max_px,
            "top_ratio": row.watermark_top_ratio,
        },
        "badge": {
            "color": row.badge_color,
            "font_size_px": row.badge_font_size_px,
        },
        "portrait": {
            "size_px": row.portrait_size_px,
            "min_px": row.portrait_min_px,
            "max_width_ratio": row.portrait_max_width_ratio,
            "ring_pad_px": row.portrait_ring_pad_px,
            "border_width_px": row.portrait_border_width_px,
            "border_color": row.portrait_border_color,
        },
    }


def resolve_draft(session: Session, page_id: int | None, template: str | None) -> Layout:
    """The Page's layout, with this draft's own template laid over it.

    One more level of the same `{**default, **override}` the file and the Page
    already form: `layout.yml` < `page_layout` < the draft. Null at any level
    means "keep tracking the one below", which is why a draft that has chosen
    nothing still follows the Page when the Page changes.

    Validated through `Layout` like everything else, so a stored template the
    compositor does not know fails here rather than rendering the wrong card and
    returning a perfectly valid PNG.
    """
    layout = resolve(session, page_id)
    if not template or template == layout.template:
        return layout
    return Layout.model_validate({**layout.model_dump(), "template": template})


def resolve(session: Session, page_id: int | None) -> Layout:
    """The layout to render this Page with. `None` gives the file's defaults.

    Validated through the same `Layout` model the file is, so a stored value
    that cannot make a layout fails here rather than inside resvg — which does
    not fail, it renders something wrong and returns a valid PNG.
    """
    if page_id is None:
        return defaults

    row = session.exec(
        select(PageLayout).where(PageLayout.page_id == page_id)
    ).first()
    if row is None:
        return defaults

    return Layout.model_validate(
        _merge(defaults.model_dump(), as_overrides(row))
    )
