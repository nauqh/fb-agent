"""Measure, wrap, plan the panel. Pure functions — a font file is the only input.

The compositor's arithmetic half, split out because it is the half that can be
tested for nothing. Every number the composite depends on is decided here: how
many lines the overlay wraps to, how tall the panel grows, and which runs of
each line render gold.

Ported from the old repo's `overlay-layout-plan.ts` and the segmenter in
`overlay-text-panel-svg.ts`. The geometry is verified rather than invented — a
real History Retraced post replays through `layout.yml` to its own 6 lines, 45px
line height and 300px panel. `tests/test_image_text.py` keeps that post as the
golden fixture.

Two deliberate departures from the port are marked below: `normalise` runs
*before* measurement rather than after, and its sentence-splitting rule refuses
to fire on acronyms.
"""

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from fontTools.ttLib import TTFont

from app.settings import Layout
from app.settings import layout as default_layout

WIDTH_SAFETY = 0.99
"""Wrap against 99% of the available width, never 100%.

`arialWrapMetrics` in the old repo returns exactly this once an exact measurer
is supplied and the padding is non-zero, which is our case (5px each side). The
1% absorbs the difference between an advance width and the ink the rasteriser
actually lays down; without it a line that measures to the pixel can still clip.
The larger safety factors in that function are for the *estimated* measurer —
`token.length * fontSize * 0.52` — which we never use, because we measure.
"""


class Measurer:
    """Advance width in pixels, mirroring opentype.js `getAdvanceWidth`.

    Sum each glyph's advance in font units, add the kern pair between adjacent
    glyphs, scale by `font_size / unitsPerEm`.

    **Kerning is not optional.** opentype.js applies it by default, and dropping
    it silently widens capital-heavy text — `AVATAR` measures 10.69px too wide at
    36px, which is Arial's AV/VA/AT/TA pairs at -152 units over a 2048 em. A
    token measured too wide wraps a line early, which changes the line count,
    which changes the panel height. The error compounds; it does not average out.

    Matches opentype.js to four decimal places on every token tried — see
    `tests/spike_text_render.py`, which stays runnable for exactly that.
    """

    def __init__(self, font_path: Path) -> None:
        self._font = TTFont(str(font_path), lazy=True)
        self._units_per_em = self._font["head"].unitsPerEm
        self._hmtx = self._font["hmtx"]
        self._cmap = self._font.getBestCmap()
        self._notdef = self._font.getGlyphOrder()[0]
        self._kern: dict[tuple[str, str], int] = {}
        if "kern" in self._font:
            for subtable in self._font["kern"].kernTables:
                self._kern.update(subtable.kernTable)

    def _glyph(self, char: str) -> str:
        return self._cmap.get(ord(char), self._notdef)

    def width(self, text: str, font_size_px: float) -> float:
        if not text:
            return 0.0
        scale = font_size_px / self._units_per_em
        glyphs = [self._glyph(char) for char in text]
        total = sum(self._hmtx[glyph][0] for glyph in glyphs)
        total += sum(
            self._kern.get(pair, 0) for pair in zip(glyphs, glyphs[1:], strict=False)
        )
        return total * scale


@lru_cache(maxsize=2)
def get_measurer(font_path: str) -> Measurer:
    """One `TTFont` per file. Re-parsing it per draft would be the slow part."""
    return Measurer(Path(font_path))


# --- normalising -------------------------------------------------------------

_SENTENCE_END = re.compile(r"(?<=[a-z]{2})\.(?=[A-Za-z])")
"""Two lowercase letters before the period, so `U.S.` and `e.g.` are left alone.

The port's rule was a bare `\\.([A-Za-z])`, which turns `U.S.` into `U. S.` and
`e.g.` into `e. g.`. On a history page that is not a hypothetical input. The
lookbehind still fixes what the rule was written for — a model returning
`tomb.The` — and declines every abbreviation, which is the only case it got
wrong.
"""

_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    # No space before closing punctuation.
    (re.compile(r"[ \t]+([,.;:!?\)\]\}])"), r"\1"),
    # The port also closed the gap *before* an opening quote — its own comment
    # gives the example `the "Seven` -> `the"Seven`. That is not English, and it
    # showed up on the first real post as `dismissed it as mere"girl talk."`
    # Dropped rather than ported; the rule below still closes the gap after the
    # quote, which is the half that was ever right.
    # No space before a closing quote: Wonders " . -> Wonders".
    (
        re.compile(r"([A-Za-z0-9])[ \t]+([\"'”’])(?=[ \t,.;:!?\)\]\}]|$)"),
        r"\1\2",
    ),
    # A space before an opening paren: word( -> word (
    (re.compile(r"([A-Za-z0-9])\("), r"\1 ("),
    # No space after an opening bracket.
    (re.compile(r"([(\[])[ \t]+"), r"\1"),
    # No space after an opening quote.
    (re.compile(r"(^|[ \t(\[{])\"[ \t]+(?=[A-Za-z0-9])"), r'\1"'),
    (re.compile(r"(^|[ \t(\[{])'[ \t]+(?=[A-Za-z0-9])"), r"\1'"),
    (re.compile(r"“[ \t]+(?=[A-Za-z0-9])"), "“"),
    (re.compile(r"‘[ \t]+(?=[A-Za-z0-9])"), "‘"),
    # One space after separating punctuation. The comma rule skips digits so
    # `2,000-year-old` survives — it is in the sample overlay text.
    (re.compile(r",([^\s\d])"), r", \1"),
    (re.compile(r";([^\s])"), r"; \1"),
    (re.compile(r":([^\s])"), r": \1"),
    (_SENTENCE_END, ". "),
)


def normalise(text: str) -> str:
    """Punctuation spacing and one flowing paragraph, ready to measure.

    **Runs before wrapping, unlike the port.** The old repo wrapped the raw text
    and then applied this per line inside `buildTextBlockElement`, so any rule
    that changes a line's length — `word(` gaining a space, `tomb.The` gaining
    another — widened a line *after* it had been measured to fit. Normalising
    first means the string that is measured is the string that is drawn.
    """
    result = text.replace(" ", " ")  # NBSP, which never wraps and measures apart
    for pattern, replacement in _RULES:
        result = pattern.sub(replacement, result)
    return re.sub(r"\s+", " ", result).strip()


# --- wrapping ----------------------------------------------------------------


def wrap(text: str, max_width_px: float, font_size_px: float, measurer: Measurer) -> list[str]:
    """Greedy word wrap on measured advance widths.

    A word too wide for the line on its own is broken mid-word rather than
    allowed to overflow — a single unbroken token is the one case where wrapping
    cannot help, and clipping it would lose text silently.
    """
    words = [word for word in normalise(text).split(" ") if word]
    if not words:
        return []

    def measure(token: str) -> float:
        return measurer.width(token, font_size_px)

    space = measure(" ")
    lines: list[str] = []
    current = ""
    current_width = 0.0

    def flush() -> None:
        nonlocal current, current_width
        if current:
            lines.append(current)
            current = ""
            current_width = 0.0

    for word in words:
        word_width = measure(word)

        if word_width > max_width_px:
            flush()
            remaining = word
            while remaining:
                take = 1
                while take < len(remaining) and measure(remaining[: take + 1]) <= max_width_px:
                    take += 1
                lines.append(remaining[:take])
                remaining = remaining[take:]
            continue

        added = space + word_width if current else word_width
        if current and current_width + added > max_width_px:
            flush()
            current, current_width = word, word_width
            continue

        current = f"{current} {word}" if current else word
        current_width += added

    flush()
    return lines


# --- highlight segmentation --------------------------------------------------


@dataclass(frozen=True)
class Segment:
    """A run of one line that renders in one colour."""

    text: str
    highlight: bool


def segment(line: str, phrases: list[str]) -> list[Segment]:
    """Split a line into gold and white runs.

    Longest phrase first, so `ocean floor` wins over `ocean` where both were
    marked and the shorter one would otherwise consume the prefix and leave
    `floor` white. Matching is case-insensitive and the matched text is kept
    verbatim, so the line's own casing survives.
    """
    if not phrases:
        return [Segment(line, False)]

    segments = [Segment(line, False)]
    for phrase in sorted((p for p in phrases if p.strip()), key=len, reverse=True):
        pattern = re.compile(re.escape(phrase), re.IGNORECASE)
        nxt: list[Segment] = []
        for part in segments:
            if part.highlight:
                nxt.append(part)
                continue
            cursor = 0
            for match in pattern.finditer(part.text):
                if match.start() > cursor:
                    nxt.append(Segment(part.text[cursor : match.start()], False))
                nxt.append(Segment(match.group(0), True))
                cursor = match.end()
            if cursor < len(part.text):
                nxt.append(Segment(part.text[cursor:], False))
        segments = [part for part in nxt if part.text]

    return _merge(segments) if segments else [Segment(line, False)]


def _merge(segments: list[Segment]) -> list[Segment]:
    """Adjacent runs of the same colour become one tspan rather than several."""
    merged: list[Segment] = []
    for part in segments:
        if merged and merged[-1].highlight == part.highlight:
            merged[-1] = Segment(merged[-1].text + part.text, part.highlight)
        else:
            merged.append(part)
    return merged


def split_by_wrap(text: str, lines: list[str], phrases: list[str]) -> list[str]:
    """Phrases that are verbatim in the overlay but land across a line break.

    Segmentation runs per line, so a phrase the wrap divided matches nothing on
    either side and renders no gold at all. `generate.py` already warns about a
    phrase that is not verbatim in the hook; this is the other way to lose
    the highlight, and it is invisible until someone looks at the picture.
    """
    normalised = normalise(text)
    lost: list[str] = []
    for phrase in phrases:
        if not phrase.strip():
            continue
        in_source = phrase.lower() in normalised.lower()
        on_a_line = any(phrase.lower() in line.lower() for line in lines)
        if in_source and not on_a_line:
            lost.append(phrase)
    return lost


# --- the plan ----------------------------------------------------------------


@dataclass(frozen=True)
class OverlayPlan:
    """Every number the compositor needs, and nothing it can recompute wrong."""

    lines: list[str]
    font_size_px: int
    line_height_px: int
    panel_height_px: int
    hero_height_px: int
    content_height_px: int
    """What the text wants, before `max_ratio` gets a say."""

    lost_highlights: list[str]

    @property
    def is_clipped(self) -> bool:
        """Whether the text needs more panel than `max_ratio` allows.

        True means lines are drawn outside the panel's clip path and the tail of
        the overlay is simply not on the image. The writer's 65-word cap makes
        this hard to reach; the compositor still refuses to render it, because
        the failure mode is a sentence that stops mid-word on a finished post.
        """
        return self.content_height_px > self.panel_height_px


def plan(text: str, phrases: list[str], layout: Layout | None = None) -> OverlayPlan:
    """Wrap the overlay and size the panel around it.

    The panel is a floor that grows, not a fixed band: `panel.ratio` is the
    minimum share of the image it takes and `panel.max_ratio` the most. The font
    never shrinks to fit — there is no autofit, by design. The hero takes
    whatever height is left, which is why the image-gen prompt hint and this
    number come from the same config.
    """
    layout = layout or default_layout
    measurer = get_measurer(str(layout.font_file))

    padding = layout.text.padding
    available = max(1, layout.image.width - padding.left_px - padding.right_px)
    font_size = layout.text.font_size_px
    line_height = round(font_size * layout.text.line_height_ratio)

    lines = wrap(text, available * WIDTH_SAFETY, font_size, measurer)

    floor = round(layout.image.height * layout.panel.ratio)
    ceiling = max(floor, round(layout.image.height * layout.panel.max_ratio))
    content = len(lines) * line_height + padding.top_px + padding.bottom_px
    panel_height = min(ceiling, max(floor, content))

    return OverlayPlan(
        lines=lines,
        font_size_px=font_size,
        line_height_px=line_height,
        panel_height_px=panel_height,
        hero_height_px=layout.image.height - panel_height,
        content_height_px=content,
        lost_highlights=split_by_wrap(text, lines, phrases),
    )
