"""Hero + black panel + gold highlights + watermark + inset, at 896×1120.

The rasterising half. `text.py` decided every number this file uses; here it
only draws. Geometry is ported from `image-composite.ts` — cover-crop the hero,
panel below it, watermark top-right of the hero inset by the edge margin, and
the circular portrait bottom-right, straddling the seam between the two.

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
from typing import NamedTuple

import resvg_py
from PIL import Image, ImageDraw

from app.image.text import OverlayPlan, Segment, segment_lines
from app.settings import API_DIR, Layout
from app.settings import layout as default_layout


JPEG_QUALITY = 92
"""The old system's number (`portrait-inset.ts:79`). 4.5× smaller, no visible loss.

Measured across the composites this repo had accumulated: 1.21MB as PNG against
0.27MB as JPEG, for the same picture. Nothing reads a composite except the review
screen and Facebook, and the publish step used to convert to JPEG on the way out
anyway — so storing PNG meant paying for the large file and then throwing it
away. Emitting JPEG here deletes that conversion instead of moving it.
"""


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
    left, right = padding.left_px, width - padding.right_px
    # `text-anchor` is the whole of alignment in SVG — there is no text-align —
    # so the anchor and the x it hangs from move together. This was hardcoded to
    # the centre while `text.align` was served, stored and offered as a control,
    # which made the control a no-op: the API answered 200, the screen showed
    # "left", and the card came back centred.
    anchor, x = {
        "left": ("start", left),
        "center": ("middle", (left + right) / 2),
        "right": ("end", right),
    }[layout.text.align]
    start_y = plan.font_size_px + padding.top_px

    coloured = segment_lines(plan.lines, phrases)
    lines = "".join(
        f'<tspan x="{x}" dy="{0 if i == 0 else plan.line_height_px}">'
        f"{_tspans(runs, layout)}</tspan>"
        for i, runs in enumerate(coloured)
    )

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">'
        f'<rect width="{width}" height="{height}" fill="{layout.panel.color}" '
        f'fill-opacity="{layout.panel.opacity}"/>'
        f'<clipPath id="panel"><rect x="{padding.left_px}" y="{padding.top_px}" '
        f'width="{width - padding.left_px - padding.right_px}" '
        f'height="{height - padding.top_px - padding.bottom_px}"/></clipPath>'
        f'<g clip-path="url(#panel)">'
        f'<text xml:space="preserve" x="{x}" y="{start_y}" text-anchor="{anchor}" '
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


def _watermark(source: str | bytes | None, box_px: int) -> Image.Image | None:
    """The page's logo, scaled to fit `box_px`. Never enlarged past its own size.

    Two kinds of source, because a Page's mark can be either a committed asset
    under `api/assets/` — a `str` path, relative to `API_DIR` — or one the
    operator uploaded, which arrives as the `bytes` its caller already fetched
    from the bucket. Fetching is the caller's job: this module draws, and a
    compositor that could reach for a bucket object is a compositor that fails
    with a network error inside a render.

    Raises `CompositeError` when a source is configured but unreadable — see the
    module docstring. `None` means the Page has no logo, which is a choice.
    """
    if not source:
        return None

    try:
        if isinstance(source, bytes):
            image = Image.open(io.BytesIO(source)).convert("RGBA")
        else:
            image = Image.open(API_DIR / source).convert("RGBA")
    except OSError as error:
        named = "the uploaded watermark" if isinstance(source, bytes) else repr(source)
        raise CompositeError(
            f"watermark {named} did not load ({error}). The image is not "
            f"composed without it — a missing logo must not ship silently."
        ) from error

    scale = min(box_px / image.width, box_px / image.height, 1.0)
    if scale < 1.0:
        image = image.resize(
            (round(image.width * scale), round(image.height * scale)), Image.LANCZOS
        )
    return image


def watermark_text_svg(text: str, layout: Layout) -> str:
    """The Page's name, set to stand in for a logo it does not have.

    Ported from `buildWatermarkSvg` (image-composite.ts:108) including its
    numbers: `0.022 × width` for the size with a 16px floor, right-anchored, 95%
    white. At 896px that is 20px type — small, and meant to be: it is a credit,
    not a brand mark, and anything larger reads as a caption on the photograph.

    The margin is ours (`edge_margin_ratio`, 18px) rather than the old file's
    own `0.022 × width` (20px), so the text and an image mark hang off the same
    edge. Two pixels, and worth the consistency.
    """
    size = max(16, round(layout.image.width * 0.022))
    margin = round(layout.image.width * layout.image.edge_margin_ratio)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{layout.image.width}" '
        f'height="{round(size * 2.2)}">'
        f'<text x="{layout.image.width - margin}" y="{round(size * 1.2)}" '
        f'text-anchor="end" font-family="{layout.font.family}" '
        f'font-weight="{layout.font.weight}" font-size="{size}" '
        f'fill="#ffffff" opacity="0.95">{_escape(text)}</text></svg>'
    )


def _watermark_text(text: str, layout: Layout) -> Image.Image:
    png = bytes(
        resvg_py.svg_to_bytes(
            svg_string=watermark_text_svg(text, layout),
            font_files=[str(layout.font_file)],
        )
    )
    return Image.open(io.BytesIO(png)).convert("RGBA")


SUPERSAMPLE = 4
"""Draw the disc and its ring this much larger, then shrink.

PIL has no antialiased ellipse. A circle drawn at final size against a black
panel has visibly stepped edges at feed size; the old app got smooth ones for
free because sharp rasterised an SVG mask. Four is where the stair-stepping
stops being visible at 140px.
"""


def circular_portrait(
    data: bytes, layout: Layout, size_px: int | None = None
) -> Image.Image:
    """The inset: a cover-cropped picture in a disc, with a ring around it.

    The ring is a stroke *centred on the circle edge*, matching the old app's
    `buildCircularPortrait` — half of it sits over the picture and half outside,
    which is why the canvas is `ring_pad_px` larger on every side. It is black,
    so the half that crosses the panel disappears into it and the disc reads as
    a cut-out rather than a sticker.

    `size_px` is the draft's chosen diameter, clamped here as well as on write:
    a row can predate a change to the bounds in `layout.yml`.
    """
    portrait = layout.portrait
    diameter = portrait.clamp(size_px, layout.image.width)
    size = portrait.ring_size(size_px, layout.image.width)

    try:
        source = Image.open(io.BytesIO(data)).convert("RGBA")
    except OSError as error:
        raise CompositeError(f"the inset portrait did not decode ({error})") from error

    face = _cover(source, diameter, diameter)
    mask = Image.new("L", (diameter * SUPERSAMPLE,) * 2, 0)
    ImageDraw.Draw(mask).ellipse(
        (0, 0, diameter * SUPERSAMPLE - 1, diameter * SUPERSAMPLE - 1), fill=255
    )
    face.putalpha(mask.resize((diameter, diameter), Image.LANCZOS))

    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.paste(face, (portrait.ring_pad_px, portrait.ring_pad_px), face)

    ring = Image.new("RGBA", (size * SUPERSAMPLE,) * 2, (0, 0, 0, 0))
    centre = size * SUPERSAMPLE / 2
    radius = (diameter / 2 + portrait.border_width_px / 2) * SUPERSAMPLE
    ImageDraw.Draw(ring).ellipse(
        (centre - radius, centre - radius, centre + radius, centre + radius),
        outline=portrait.border_color,
        width=round(portrait.border_width_px * SUPERSAMPLE),
    )
    canvas.alpha_composite(ring.resize((size, size), Image.LANCZOS))
    return canvas


class Inset(NamedTuple):
    """The uploaded circle and where it goes. One argument, because the three
    travel together and a `compose(..., None, None, None)` says nothing."""

    data: bytes
    size_px: int | None = None
    x_ratio: float | None = None
    y_ratio: float | None = None


def inset_centre(
    inset: Inset, plan: OverlayPlan, layout: Layout
) -> tuple[int, int]:
    """Where the disc's centre lands, in card pixels.

    A null ratio resolves *here* rather than on the row, because the default
    depends on the draft: the panel grows with the copy, so the seam is at a
    different height on every card. Bottom-right at the edge margin, centred on
    the seam — `portraitTop`/`portraitLeft` in `brand-image-layout.ts:139-140`,
    converted from a corner to a centre.
    """
    width, height = layout.image.width, layout.image.height
    ring = layout.portrait.ring_size(inset.size_px, width)
    margin = round(width * layout.image.edge_margin_ratio)

    x = width - margin - ring / 2 if inset.x_ratio is None else inset.x_ratio * width
    y = plan.hero_height_px if inset.y_ratio is None else inset.y_ratio * height
    return round(x), round(y)


def compose(
    hero: bytes,
    plan: OverlayPlan,
    phrases: list[str],
    watermark: str | bytes | None,
    inset: Inset | None = None,
    layout: Layout | None = None,
    fallback_text: str | None = None,
) -> bytes:
    """The finished JPEG. Everything variable was decided before this call."""
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

    margin = round(width * layout.image.edge_margin_ratio)

    box = min(layout.watermark.max_px, round(width * 0.22))
    mark = _watermark(watermark, box)
    top = max(8, round(plan.hero_height_px * layout.watermark.top_ratio))
    if mark is not None:
        canvas.paste(mark, (width - mark.width - margin, top), mark)
    elif fallback_text:
        # Only when the Page has *no* mark configured at all. A configured one
        # that will not load raised above and never reaches here — that order is
        # the whole difference from the old compositor, which fell through to
        # this branch on a failed load and printed the name for eight months
        # while looking like it was working.
        #
        # Eight of the ten Pages have no logo, and unmarked output is how a
        # picture ends up reposted with no idea where it came from. The name is
        # not as good as the wordmark; it is much better than nothing.
        drawn = _watermark_text(fallback_text, layout)
        canvas.alpha_composite(drawn, (0, top))

    if inset is not None:
        # Default is centred on the seam: half on the photograph, half on the
        # panel. That overlap is the effect — a disc wholly inside the hero is a
        # sticker, and one wholly inside the panel is an avatar. The operator
        # can drag it anywhere from there.
        disc = circular_portrait(inset.data, layout, inset.size_px)
        x, y = inset_centre(inset, plan, layout)
        canvas.alpha_composite(disc, (x - disc.width // 2, y - disc.height // 2))

    out = io.BytesIO()
    # `convert("RGB")` on a canvas that still had transparency would composite
    # it onto *black* without saying so. Safe here only because the hero and the
    # panel between them cover every pixel — the same assumption the publish
    # step's flatten-onto-white made explicit before it was deleted. If a layout
    # ever leaves a gap, this is where it turns into a black band.
    canvas.convert("RGB").save(out, format="JPEG", quality=JPEG_QUALITY)
    return out.getvalue()
