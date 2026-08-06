"""Hero + black panel + gold highlights + watermark, at 896×1120.

The rasterising half. `text.py` decided every number this file uses; here it
only draws. Geometry is ported from `image-composite.ts` — cover-crop the hero,
panel below it, watermark top-right of the hero inset by the edge margin.

Two things are deliberate and easy to undo by accident:

- **Corners are square.** The old code computes a radius and then hardcodes
  `const cornerRadius = 0` (`image-composite.ts:313`). Facebook must not get a
  rounded card. Do not reintroduce it.
- **A configured watermark that will not load raises.** The old compositor
  returned `null` there and quietly printed the page name as text instead, which
  is how History Retraced lost its logo for weeks without one failed post. The
  text fallback is only for a Page with no logo at all.
"""

import io
from pathlib import Path

import resvg_py
from PIL import Image

from app.image.text import OverlayPlan, Segment, segment
from app.settings import API_DIR, Layout
from app.settings import layout as default_layout


class CompositeError(RuntimeError):
    """The image cannot be drawn. Lands on `draft.error`, never swallowed."""


def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _tspans(segments: list[Segment], layout: Layout) -> str:
    parts = []
    for part in segments:
        fill = layout.highlight.color if part.highlight else layout.text.color
        # Runs of spaces collapse in SVG text unless they are non-breaking.
        content = _escape(part.text).replace(" ", "&#160;")
        parts.append(f'<tspan fill="{fill}">{content}</tspan>')
    return "".join(parts)


def panel_svg(plan: OverlayPlan, phrases: list[str], layout: Layout) -> str:
    """The text panel, exactly as the rasteriser will see it.

    `font-family` must be the TTF's own name-table entry — `Arial` with
    `font-weight="bold"`, never `"Arial Bold"`. resvg does not error on an
    unmatched family; it substitutes a system face and returns a valid PNG of
    the wrong font, which then disagrees with every width `text.py` measured.
    `render_panel` asserts the ink width for that reason.
    """
    padding = layout.text.padding
    width = layout.image.width
    height = plan.panel_height_px
    x = (padding.left_px + (width - padding.right_px)) / 2
    start_y = plan.font_size_px + padding.top_px

    lines = "".join(
        f'<tspan x="{x}" dy="{0 if i == 0 else plan.line_height_px}">'
        f"{_tspans(segment(line, phrases), layout)}</tspan>"
        for i, line in enumerate(plan.lines)
    )

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">'
        f'<rect width="{width}" height="{height}" fill="{layout.panel.color}" '
        f'fill-opacity="{layout.panel.opacity}"/>'
        f'<clipPath id="panel"><rect x="{padding.left_px}" y="{padding.top_px}" '
        f'width="{width - padding.left_px - padding.right_px}" '
        f'height="{height - padding.top_px - padding.bottom_px}"/></clipPath>'
        f'<g clip-path="url(#panel)">'
        f'<text xml:space="preserve" x="{x}" y="{start_y}" text-anchor="middle" '
        f'font-family="{layout.font.family}" font-weight="{layout.font.weight}" '
        f'font-size="{plan.font_size_px}" fill="{layout.text.color}">{lines}</text>'
        f"</g></svg>"
    )


def render_panel(plan: OverlayPlan, phrases: list[str], layout: Layout) -> Image.Image:
    svg = panel_svg(plan, phrases, layout)
    png = bytes(
        resvg_py.svg_to_bytes(svg_string=svg, font_files=[str(layout.font_file)])
    )
    return Image.open(io.BytesIO(png)).convert("RGBA")


def _cover(image: Image.Image, width: int, height: int) -> Image.Image:
    """Fill the box, crop the overflow, centred — sharp's `fit: cover`.

    Needed because the hero cannot be ordered at an exact size: Gemini takes an
    aspect ratio, not dimensions, and returns its own resolution near it.
    """
    scale = max(width / image.width, height / image.height)
    resized = image.resize(
        (max(width, round(image.width * scale)), max(height, round(image.height * scale))),
        Image.LANCZOS,
    )
    left = (resized.width - width) // 2
    top = (resized.height - height) // 2
    return resized.crop((left, top, left + width, top + height))


def _watermark(path: str | None, box_px: int) -> Image.Image | None:
    """The page's logo, scaled to fit `box_px`. Never enlarged past its own size.

    Raises `CompositeError` when a path is configured but unreadable — see the
    module docstring. `None` means the Page has no logo, which is a choice.
    """
    if not path:
        return None

    resolved = API_DIR / path
    try:
        image = Image.open(resolved).convert("RGBA")
    except OSError as error:
        raise CompositeError(
            f"watermark {path!r} did not load ({error}). The image is not "
            f"composed without it — a missing logo must not ship silently."
        ) from error

    scale = min(box_px / image.width, box_px / image.height, 1.0)
    if scale < 1.0:
        image = image.resize(
            (round(image.width * scale), round(image.height * scale)), Image.LANCZOS
        )
    return image


def compose(
    hero: bytes,
    plan: OverlayPlan,
    phrases: list[str],
    watermark_path: str | None,
    layout: Layout | None = None,
) -> bytes:
    """The finished PNG. Everything variable was decided before this call."""
    layout = layout or default_layout

    if not plan.lines:
        raise CompositeError("the overlay text produced no lines to draw")
    if plan.is_clipped:
        raise CompositeError(
            f"the overlay needs {plan.content_height_px}px of panel and the "
            f"maximum is {plan.panel_height_px}px; it would be cut off mid-word"
        )

    width = layout.image.width
    canvas = Image.new("RGBA", (width, layout.image.height))

    try:
        source = Image.open(io.BytesIO(hero)).convert("RGBA")
    except OSError as error:
        raise CompositeError(f"the hero image did not decode ({error})") from error

    canvas.paste(_cover(source, width, plan.hero_height_px), (0, 0))
    canvas.paste(render_panel(plan, phrases, layout), (0, plan.hero_height_px))

    box = min(layout.watermark.max_px, round(width * 0.22))
    mark = _watermark(watermark_path, box)
    if mark is not None:
        margin = round(width * layout.image.edge_margin_ratio)
        top = max(8, round(plan.hero_height_px * layout.watermark.top_ratio))
        canvas.paste(mark, (width - mark.width - margin, top), mark)

    out = io.BytesIO()
    canvas.convert("RGB").save(out, format="PNG")
    return out.getvalue()
