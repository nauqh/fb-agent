"""Phase 0 spike — does the Python text stack match the TypeScript one?

Two questions, both blocking Phase 4:

  1. Does `fontTools` reproduce `opentype.js`'s `getAdvanceWidth`? Wrapping is
     decided by these numbers, so a drift of a few pixels per token compounds
     into a different line count and a differently sized panel.
  2. Can `resvg-py` rasterise SVG text using a *local* TTF on Windows?

Reference widths were produced by the old repo at 36px:
    node -e '...opentype.js getAdvanceWidth(token, 36)...'

Run:  uv run python tests/spike_text_render.py
"""

from pathlib import Path

from fontTools.ttLib import TTFont

API_DIR = Path(__file__).resolve().parent.parent
FONT = API_DIR / "assets" / "fonts" / "Arial-Bold.ttf"
OUT = API_DIR / "media" / "spike"

# token -> opentype.js getAdvanceWidth(token, 36)
REFERENCE = {
    "The": 64.0020,
    "Smithsonian": 216.0176,
    "archaeologists": 254.0918,
    "1923": 80.0859,
    "W": 33.9785,
    "i": 10.0020,
    "In 1923, archaeologists": 396.1758,
    "fig.": 53.9824,
    "AVATAR": 139.3066,
    "quick brown fox": 276.0117,
}
TOLERANCE_PX = 0.01


class Measurer:
    """Advance width in pixels, mirroring opentype.js `getAdvanceWidth`.

    Sum each glyph's advance in font units, add the kern pair between adjacent
    glyphs, scale by fontSize / unitsPerEm.

    Kerning is *not* optional. opentype.js applies it by default, and dropping
    it silently widens capital-heavy text — "AVATAR" measured 10.69px too wide,
    which is `kern`'s AV/VA/AT/TA pairs at -152 units each over a 2048 em.
    A token measured too wide wraps a line early, which changes the line count,
    which changes the panel height. The error compounds; it does not average out.
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


def check_measurement() -> bool:
    measurer = Measurer(FONT)
    print(f"{'delta':>10}  {'fontTools':>10}  {'opentype':>10}  token")
    worst = 0.0
    for token, expected in REFERENCE.items():
        got = measurer.width(token, 36)
        delta = abs(got - expected)
        worst = max(worst, delta)
        flag = " " if delta <= TOLERANCE_PX else "  <-- DRIFT"
        print(f"{delta:>10.4f}  {got:>10.4f}  {expected:>10.4f}  {token!r}{flag}")
    print(f"\nworst drift: {worst:.4f}px  (tolerance {TOLERANCE_PX}px)")
    return worst <= TOLERANCE_PX


def _render(svg: str) -> "Image.Image":
    import resvg_py
    from PIL import Image

    OUT.mkdir(parents=True, exist_ok=True)
    png = bytes(resvg_py.svg_to_bytes(svg_string=svg, font_files=[str(FONT)]))
    target = OUT / "spike-last.png"
    target.write_bytes(png)
    return Image.open(target).convert("RGB")


def _ink_width(image: "Image.Image") -> int:
    """Width of the drawn glyphs, ignoring the black plate."""
    box = image.getbbox()  # non-black bounding box
    return 0 if box is None else box[2] - box[0]


def check_render() -> bool:
    """Rasterise SVG text with the local TTF, the way the compositor will.

    The trap this guards: resvg does not fail when it cannot match a
    `font-family`. It silently substitutes a system face and returns a
    perfectly good PNG of the wrong font — which then disagrees with every
    width fontTools measured, so the wrapping is right for a font that is not
    on screen. The family here must be the TTF's own name table entry
    ("Arial" / "Bold"), not the file name ("Arial Bold").

    Detection is by measurement, not by eye: the rendered ink must be no wider
    than the advance width fontTools computed, and within a few pixels of it.
    """
    from PIL import Image  # noqa: F401 — imported for the type in _render

    sample = "In 1923, archaeologists opened a sealed tomb"
    expected = Measurer(FONT).width(sample, 36)

    def plate(family: str, weight: str) -> str:
        return f"""<svg xmlns="http://www.w3.org/2000/svg" width="896" height="80">
  <rect width="896" height="80" fill="#000000"/>
  <text x="0" y="52" font-family="{family}" font-weight="{weight}"
        font-size="36" fill="#ffffff">{sample}</text>
</svg>"""

    good = _ink_width(_render(plate("Arial", "bold")))
    (OUT / "spike-last.png").replace(OUT / "spike-arial-bold.png")
    bogus = _ink_width(_render(plate("NoSuchFace", "normal")))
    (OUT / "spike-last.png").replace(OUT / "spike-fallback.png")

    drift = abs(good - expected)
    print(f"measured advance : {expected:8.2f}px")
    print(f"rendered ink     : {good:8d}px   drift {drift:.2f}px")
    print(f"unmatched family : {bogus:8d}px   (system fallback, for contrast)")

    matched = drift <= 4 and good != bogus
    if not matched:
        print("  <-- resvg is not using the local TTF; it fell back silently")

    # The real panel, now with the family that actually resolves.
    panel = f"""<svg xmlns="http://www.w3.org/2000/svg" width="896" height="224">
  <rect width="896" height="224" fill="#000000"/>
  <text x="448" y="90" font-family="Arial" font-weight="bold" font-size="36"
        fill="#ffffff" text-anchor="middle">In 1923, archaeologists opened</text>
  <text x="448" y="150" font-family="Arial" font-weight="bold" font-size="36"
        fill="#F5C542" text-anchor="middle">a sealed tomb</text>
</svg>"""
    image = _render(panel)
    (OUT / "spike-last.png").replace(OUT / "spike-panel.png")
    gold = sum(
        1
        for pixel in image.getdata()
        if abs(pixel[0] - 0xF5) < 12
        and abs(pixel[1] - 0xC5) < 12
        and abs(pixel[2] - 0x42) < 12
    )
    print(f"\nwrote {OUT / 'spike-panel.png'}  {image.width}x{image.height}")
    print(f"gold highlight pixels: {gold}")

    return matched and image.size == (896, 224) and gold > 200


if __name__ == "__main__":
    print("== 1. fontTools vs opentype.js ==")
    measured = check_measurement()
    print("\n== 2. resvg-py with a local TTF ==")
    rendered = check_render()
    print(
        f"\nRESULT  measurement={'PASS' if measured else 'FAIL'}  "
        f"render={'PASS' if rendered else 'FAIL'}"
    )
    raise SystemExit(0 if (measured and rendered) else 1)
