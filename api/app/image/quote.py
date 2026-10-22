"""The `quote` card: the hook set as type on a dark ground. No hero, no panel.

Modelled on the posts the client pointed at (2026-10-22, Inspire Through
Bible): a gold quotation mark beside the Page's name, a heading in capitals,
then the quote, left-aligned on a near-black grain, the block centred on the
card. Everything is drawn here, so a quote card buys no picture and redraws for
free like any other edit.

The hook carries both texts. With more than one line the first is the heading
("PSALM 94:19", "MARCUS AURELIUS"); with one line it is all quote. Highlight
phrases are set in bold italic rather than gold, which is the sample's emphasis.

No autofit, as on the panel (`text.plan`): a quote too long for the card is
refused rather than shrunk, so the preview and the PNG agree on the type size.
"""

import io
from dataclasses import dataclass

import resvg_py
from PIL import Image

from app.image.compositor import JPEG_QUALITY, CompositeError, _escape, _watermark
from app.image.text import WIDTH_SAFETY, Measurer, Segment, _merge, get_measurer, segment
from app.settings import API_DIR, Layout

HEADING_LINE_RATIO = 1.1
NAME_RATIO = 0.2
"""The Page's name beside the quotation mark, as a share of the mark's size."""


def split(hook: str) -> tuple[str | None, str]:
    """The heading and the quote. No heading unless the hook has two lines.

    Whitespace is collapsed and nothing else. `text.normalise` puts a space
    after every colon, which turns "Psalm 94:19" into "94: 19".
    """
    lines = [" ".join(line.split()) for line in hook.splitlines() if line.strip()]
    if len(lines) < 2:
        return None, " ".join(lines)
    return lines[0], " ".join(lines[1:])


def wrap_runs(
    text: str,
    phrases: list[str],
    max_width_px: float,
    size_px: float,
    regular: Measurer,
    emphasis: Measurer,
) -> list[list[Segment]]:
    """Greedy wrap where an emphasised word is measured in the bold italic.

    `text.wrap` measures one face. Here a line mixes two, and bold italic runs
    wider than the regular, so a line measured in one face alone overruns.
    """
    words: list[list[Segment]] = [[]]
    for run in segment(text, phrases):
        for index, piece in enumerate(run.text.split(" ")):
            if index:
                words.append([])
            if piece:
                words[-1].append(Segment(piece, run.highlight))

    def measure(word: list[Segment]) -> float:
        return sum(
            (emphasis if part.highlight else regular).width(part.text, size_px)
            for part in word
        )

    space = regular.width(" ", size_px)
    lines: list[list[Segment]] = []
    current: list[Segment] = []
    used = 0.0
    for word in (word for word in words if word):
        width = measure(word)
        if current and used + space + width > max_width_px:
            lines.append(current)
            current, used = [], 0.0
        if current:
            # Emphasised only inside a phrase, so the italic does not reach
            # into the gap before or after one.
            current.append(Segment(" ", current[-1].highlight and word[0].highlight))
            used += space
        current += word
        used += width
    if current:
        lines.append(current)
    return [_merge(line) for line in lines]


@dataclass(frozen=True)
class QuotePlan:
    """Every position the card draws at. Baselines, in card pixels."""

    heading: list[str]
    body: list[list[Segment]]
    mark_y: int
    heading_y: int
    body_y: int
    heading_line_px: int
    body_line_px: int


def plan(hook: str, phrases: list[str], layout: Layout) -> QuotePlan:
    quote = layout.quote
    width, height = layout.image.width, layout.image.height
    margin = round(width * quote.margin_ratio)
    available = (width - margin * 2) * WIDTH_SAFETY
    regular = get_measurer(str(API_DIR / quote.font_path))
    emphasis = get_measurer(str(API_DIR / quote.emphasis_path))

    heading_text, body_text = split(hook)
    # Not `text.wrap`, which normalises on its own and would put the space back.
    heading = [
        "".join(part.text for part in line)
        for line in wrap_runs(
            (heading_text or "").upper(), [], available, quote.heading_px, regular, regular
        )
    ]
    body = wrap_runs(body_text, phrases, available, quote.body_px, regular, emphasis)
    if not heading and not body:
        raise CompositeError("the quote card has no text to draw")

    heading_line = round(quote.heading_px * HEADING_LINE_RATIO)
    body_line = round(quote.body_px * quote.line_height_ratio)

    # Heights of the three blocks as the eye sees them: a quotation mark's ink
    # is the top third of its em, and a line of text is its size plus the
    # leading of every line after the first.
    mark = round(quote.mark_px * 0.4)
    heading_height = (len(heading) - 1) * heading_line + quote.heading_px if heading else 0
    body_height = (len(body) - 1) * body_line + quote.body_px if body else 0
    gap_after_mark = round(quote.heading_px * 0.5)
    gap_after_heading = round(quote.body_px * 0.5) if heading and body else 0

    total = mark + gap_after_mark + heading_height + gap_after_heading + body_height
    if total > height - margin * 2:
        raise CompositeError(
            f"the quote needs {total}px and the card has {height - margin * 2}px; "
            "shorten it"
        )
    # A touch above centre, where a centred block looks centred.
    top = round((height - total) * 0.45)
    heading_top = top + mark + gap_after_mark
    body_top = heading_top + heading_height + gap_after_heading

    return QuotePlan(
        heading=heading,
        body=body,
        # A quotation mark sits high in its em: its ink starts about 0.72em
        # above the baseline, so this puts the ink's top at `top`.
        mark_y=top + round(quote.mark_px * 0.72),
        heading_y=heading_top + round(quote.heading_px * 0.8),
        body_y=body_top + round(quote.body_px * 0.8),
        heading_line_px=heading_line,
        body_line_px=body_line,
    )


def _text(content: str) -> str:
    # Runs of spaces collapse in SVG text unless they are non-breaking.
    return _escape(content).replace(" ", "&#160;")


def card_svg(
    quote_plan: QuotePlan, layout: Layout, name: str | None, name_x: int
) -> str:
    quote = layout.quote
    width, height = layout.image.width, layout.image.height
    margin = round(width * quote.margin_ratio)
    colour = layout.text.color
    family = f'font-family="{quote.font_family}"'

    parts = [
        f'<text x="{margin}" y="{quote_plan.mark_y}" font-family="{layout.font.family}" '
        f'font-weight="{layout.font.weight}" font-size="{quote.mark_px}" '
        f'fill="{layout.highlight.color}">&#8220;</text>'
    ]
    if name:
        size = round(quote.mark_px * NAME_RATIO)
        # Centred on the mark's ink, which is the top third of its em.
        y = quote_plan.mark_y - round(quote.mark_px * 0.55) + round(size * 0.35)
        parts.append(
            f'<text x="{name_x}" y="{y}" font-family="{layout.font.family}" '
            f'font-weight="{layout.font.weight}" font-size="{size}" fill="{colour}" '
            f'fill-opacity="0.85">{_text(name)}</text>'
        )
    if quote_plan.heading:
        lines = "".join(
            f'<tspan x="{margin}" dy="{0 if i == 0 else quote_plan.heading_line_px}">'
            f"{_text(line)}</tspan>"
            for i, line in enumerate(quote_plan.heading)
        )
        parts.append(
            f'<text xml:space="preserve" x="{margin}" y="{quote_plan.heading_y}" {family} '
            f'font-size="{quote.heading_px}" fill="{colour}">{lines}</text>'
        )
    if quote_plan.body:
        lines = "".join(
            f'<tspan x="{margin}" dy="{0 if i == 0 else quote_plan.body_line_px}">'
            + "".join(
                f'<tspan font-weight="bold" font-style="italic">{_text(part.text)}</tspan>'
                if part.highlight
                else f"<tspan>{_text(part.text)}</tspan>"
                for part in runs
            )
            + "</tspan>"
            for i, runs in enumerate(quote_plan.body)
        )
        parts.append(
            f'<text xml:space="preserve" x="{margin}" y="{quote_plan.body_y}" {family} '
            f'font-size="{quote.body_px}" fill="{colour}">{lines}</text>'
        )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">'
        + "".join(parts)
        + "</svg>"
    )


def _ground(layout: Layout) -> Image.Image:
    """The background: a flat colour with gaussian grain blended over it."""
    size = (layout.image.width, layout.image.height)
    base = Image.new("RGB", size, layout.quote.background)
    grain = Image.effect_noise(size, 64).convert("RGB")
    return Image.blend(base, grain, layout.quote.grain).convert("RGBA")


def compose(
    hook: str,
    phrases: list[str],
    watermark: str | bytes | None,
    layout: Layout,
    fallback_text: str | None = None,
) -> bytes:
    """The finished JPEG. The Page's mark goes beside the quotation mark.

    The mark and its fallback text are the same decision they are on the other
    cards (`Page.watermark`): an uploaded or committed logo, else the Page's
    name, else nothing when the Page has opted out.
    """
    quote = layout.quote
    quote_plan = plan(hook, phrases, layout)
    margin = round(layout.image.width * quote.margin_ratio)
    mark_width = get_measurer(str(layout.font_file)).width("“", quote.mark_px)
    name_x = round(margin + mark_width + quote.mark_px * 0.12)

    logo = _watermark(watermark, 10_000)
    if logo is not None:
        tall = round(quote.mark_px * 0.5)
        logo = logo.resize(
            (max(1, round(logo.width * tall / logo.height)), tall), Image.LANCZOS
        )

    svg = card_svg(quote_plan, layout, None if logo else fallback_text, name_x)
    png = resvg_py.svg_to_bytes(
        svg_string=svg,
        font_files=[
            str(layout.font_file),
            str(API_DIR / quote.font_path),
            str(API_DIR / quote.emphasis_path),
        ],
    )
    canvas = _ground(layout)
    canvas.alpha_composite(Image.open(io.BytesIO(bytes(png))).convert("RGBA"))
    if logo is not None:
        ink_middle = quote_plan.mark_y - round(quote.mark_px * 0.55)
        canvas.alpha_composite(logo, (name_x, max(0, ink_middle - logo.height // 2)))

    out = io.BytesIO()
    canvas.convert("RGB").save(out, format="JPEG", quality=JPEG_QUALITY)
    return out.getvalue()
