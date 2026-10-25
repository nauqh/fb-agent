"""The `quote` card: the hook set as type on a plain ground. No hero, no panel.

Modelled on the post the client pointed at (2026-10-25): white on black, the
quote centred between two horizontal rules, an opening mark above the top rule
at the left and a closing mark below the bottom rule at the right. Who said it
sits under the quote, inside the rules; the Page's name sits under everything.
Everything is drawn here, so a quote card buys no picture and redraws for free
like any other edit.

Highlight phrases are set in bold italic, the sample's emphasis. The marks are
the draft's choice (`Draft.quote_marks`): off, the same text reads as a
statement.

No autofit, as on the panel (`text.plan`): a quote too long for the card is
refused rather than shrunk, so the preview and the PNG agree on the type size.
"""

import io
from dataclasses import dataclass

import resvg_py
from PIL import Image

from app.image.compositor import JPEG_QUALITY, CompositeError, _escape
from app.image.text import WIDTH_SAFETY, Measurer, Segment, _merge, get_measurer, segment
from app.settings import API_DIR, Layout

MARK_INK = 0.4
"""A quotation mark's ink, as a share of its em: about the top third."""
MARK_ASCENT = 0.72
"""How far above the baseline a quotation mark's ink starts, in ems."""
QUOTES = "\"“”"


def body_text(hook: str, marks: bool) -> str:
    """The quote as one paragraph. Its own quotation marks go when the card
    draws them, so a hook written in curly quotes is not quoted twice.

    Whitespace is collapsed and nothing else. `text.normalise` puts a space
    after every colon, which turns "Psalm 94:19" into "94: 19".
    """
    text = " ".join(hook.split())
    return text.strip(QUOTES).strip() if marks else text


def attribution_text(name: str | None) -> str | None:
    """`- Name -`, from a name typed with or without its own dashes."""
    # The class holds en and em dashes as data: what an operator may type.
    name = (name or "").strip(" -–—")
    return f"- {name} -" if name else None


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
    """Every position the card draws at. Baselines and rule tops, in card pixels."""

    body: list[list[Segment]]
    attribution: list[str]
    marks: bool
    name: str | None
    open_mark_y: int
    top_rule_y: int
    body_y: int
    attribution_y: int
    bottom_rule_y: int
    close_mark_y: int
    name_y: int
    body_line_px: int
    attribution_line_px: int


def plan(
    hook: str,
    phrases: list[str],
    layout: Layout,
    *,
    marks: bool = True,
    attribution: str | None = None,
    name: str | None = None,
) -> QuotePlan:
    quote = layout.quote
    width, height = layout.image.width, layout.image.height
    margin = round(width * quote.margin_ratio)
    available = (width - margin * 2) * WIDTH_SAFETY
    regular = get_measurer(str(API_DIR / quote.font_path))
    italic = get_measurer(str(API_DIR / quote.italic_path))
    emphasis = get_measurer(str(API_DIR / quote.emphasis_path))

    body = wrap_runs(body_text(hook, marks), phrases, available, quote.body_px, regular, emphasis)
    if not body:
        raise CompositeError("the quote card has no text to draw")
    credit = attribution_text(attribution)
    credit_lines = [
        "".join(part.text for part in line)
        for line in wrap_runs(credit or "", [], available, quote.attribution_px, italic, italic)
    ]

    body_line = round(quote.body_px * quote.line_height_ratio)
    credit_line = round(quote.attribution_px * quote.line_height_ratio)
    body_height = (len(body) - 1) * body_line + quote.body_px
    credit_height = (
        round(quote.body_px * 0.7) + (len(credit_lines) - 1) * credit_line + quote.attribution_px
        if credit_lines
        else 0
    )
    # Heights as the eye sees them: a mark is its ink, a line of text is its
    # size plus the leading of every line after the first.
    mark = round(quote.mark_px * MARK_INK) + round(quote.body_px * 0.35) if marks else 0
    inside = quote.body_px
    name_height = round(quote.body_px * 1.1) + quote.name_px if name else 0

    total = (
        mark * 2
        + quote.rule_px * 2
        + inside * 2
        + body_height
        + credit_height
        + name_height
    )
    if total > height - margin * 2:
        raise CompositeError(
            f"the quote needs {total}px and the card has {height - margin * 2}px; "
            "shorten it"
        )

    top = round((height - total) / 2)
    top_rule = top + mark
    body_top = top_rule + quote.rule_px + inside
    credit_top = body_top + body_height + round(quote.body_px * 0.7)
    bottom_rule = body_top + body_height + credit_height + inside
    close_top = bottom_rule + quote.rule_px + round(quote.body_px * 0.35)
    name_top = bottom_rule + quote.rule_px + mark + round(quote.body_px * 1.1)

    return QuotePlan(
        body=body,
        attribution=credit_lines,
        marks=marks,
        name=name,
        open_mark_y=top + round(quote.mark_px * MARK_ASCENT),
        top_rule_y=top_rule,
        body_y=body_top + round(quote.body_px * 0.8),
        attribution_y=credit_top + round(quote.attribution_px * 0.8),
        bottom_rule_y=bottom_rule,
        close_mark_y=close_top + round(quote.mark_px * MARK_ASCENT),
        name_y=name_top + round(quote.name_px * 0.8),
        body_line_px=body_line,
        attribution_line_px=credit_line,
    )


def _text(content: str) -> str:
    # Runs of spaces collapse in SVG text unless they are non-breaking.
    return _escape(content).replace(" ", "&#160;")


def card_svg(quote_plan: QuotePlan, layout: Layout) -> str:
    quote = layout.quote
    width, height = layout.image.width, layout.image.height
    margin = round(width * quote.margin_ratio)
    centre = width // 2
    colour = quote.color
    family = f'font-family="{quote.font_family}"'

    parts = [
        f'<rect x="{margin}" y="{y}" width="{width - margin * 2}" height="{quote.rule_px}" '
        f'fill="{colour}"/>'
        for y in (quote_plan.top_rule_y, quote_plan.bottom_rule_y)
    ]
    if quote_plan.marks:
        mark = (
            f'font-family="{layout.font.family}" font-weight="{layout.font.weight}" '
            f'font-size="{quote.mark_px}" fill="{colour}"'
        )
        parts.append(f'<text x="{margin}" y="{quote_plan.open_mark_y}" {mark}>&#8220;</text>')
        parts.append(
            f'<text x="{width - margin}" y="{quote_plan.close_mark_y}" text-anchor="end" '
            f"{mark}>&#8221;</text>"
        )

    lines = "".join(
        f'<tspan x="{centre}" dy="{0 if i == 0 else quote_plan.body_line_px}">'
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
        f'<text xml:space="preserve" x="{centre}" y="{quote_plan.body_y}" {family} '
        f'text-anchor="middle" font-size="{quote.body_px}" fill="{colour}">{lines}</text>'
    )
    if quote_plan.attribution:
        lines = "".join(
            f'<tspan x="{centre}" dy="{0 if i == 0 else quote_plan.attribution_line_px}">'
            f"{_text(line)}</tspan>"
            for i, line in enumerate(quote_plan.attribution)
        )
        parts.append(
            f'<text xml:space="preserve" x="{centre}" y="{quote_plan.attribution_y}" {family} '
            f'font-style="italic" text-anchor="middle" font-size="{quote.attribution_px}" '
            f'fill="{colour}">{lines}</text>'
        )
    if quote_plan.name:
        parts.append(
            f'<text xml:space="preserve" x="{centre}" y="{quote_plan.name_y}" {family} '
            f'text-anchor="middle" font-size="{quote.name_px}" fill="{colour}" '
            f'fill-opacity="0.85">{_text(quote_plan.name)}</text>'
        )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">'
        + "".join(parts)
        + "</svg>"
    )


def compose(
    hook: str,
    phrases: list[str],
    layout: Layout,
    name: str | None = None,
    *,
    marks: bool = True,
    attribution: str | None = None,
) -> bytes:
    """The finished JPEG.

    `name` is the Page's, as text, never its logo (client, 2026-10-25): the
    watermark's fallback text, null when the Page has opted out of a mark.
    """
    quote = layout.quote
    quote_plan = plan(hook, phrases, layout, marks=marks, attribution=attribution, name=name)
    png = resvg_py.svg_to_bytes(
        svg_string=card_svg(quote_plan, layout),
        font_files=[
            str(layout.font_file),
            str(API_DIR / quote.font_path),
            str(API_DIR / quote.italic_path),
            str(API_DIR / quote.emphasis_path),
        ],
    )
    canvas = Image.new("RGBA", (layout.image.width, layout.image.height), quote.background)
    canvas.alpha_composite(Image.open(io.BytesIO(bytes(png))).convert("RGBA"))

    out = io.BytesIO()
    canvas.convert("RGB").save(out, format="JPEG", quality=JPEG_QUALITY)
    return out.getvalue()
