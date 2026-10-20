# Card style: fade overlay, fonts, editor

Tracking doc for the 2026-10-20 request. Tick items as they land; the commit
messages carry the evidence.

## 1. Fade to black on `full_overlay`

The full overlay drew a flat rect over the photo's bottom: a hard seam through
the subject. Other pages fade the photo into black behind the text.

- [x] Compositor: on `full_overlay`, a vertical gradient above the panel,
      clear at the top to `panel.color` at `panel.opacity` where the panel
      starts. `card` is unchanged.
- [x] The fade starts above the text, so the photo darkens gradually rather
      than at the panel's top edge.
- [x] Layout editor preview mirrors it with a CSS `linear-gradient`.
- [x] Tests pin the gradient (top transparent, bottom dark).
- [x] Driven in the browser (layout editor) and rendered through `compose`.

`panel.color` and `panel.opacity` describe the end of the fade; at 0% opacity
there is no fade. Its height is `panel.fade_ratio` in `layout.yml` (0.2 of the
card), served so both renderers read one number. Not per Page yet - add a
`page_layout` column and a slider if a Page needs its own.

## 2. Choosable fonts

One font today: `api/assets/fonts/Arial-Bold.ttf`, global.

- [x] Bundle a short list of OFL fonts as static TTFs: Arial (default),
      Montserrat ExtraBold, Poppins Bold, Oswald Bold, Anton, Playfair
      Display Bold. Merriweather dropped: only a variable-font cut was at hand,
      and those carry the wrong family name.
- [x] Allowed list in code; `page_layout.font` column (null = default), migration.
- [x] Compositor, measurer, watermark and badge all use the Page's font.
- [x] Editor picker (each name drawn in its own face); preview loads the same TTFs via `@font-face` so wrapping
      matches the card.
- [x] Test per font: renders in its own face, not resvg's silent fallback.

Risks:

- resvg substitutes silently when `font-family` does not match the TTF's name
  table. Each font gets a render test.
- `Measurer` reads only the legacy `kern` table; many Google fonts kern via
  GPOS only. Widths may run slightly narrow - measure, then adjust
  `WIDTH_SAFETY` if needed.
- Caps-only faces (Bebas Neue) need `uppercase` on, or stay off the list.
  Left off.

Measured: every pick draws within 1% of its measured width (test in
`test_layout.py`), so the missing GPOS kerning has not mattered yet.

## 3. WYSIWYG editor - waiting on a decision

Two different things; which one is meant decides the cost.

- **A. Caption composer** (Postiz style): emoji, hashtag/char counters, a
  Facebook-style preview. Facebook captions are plain text, so "bold" is
  Unicode look-alikes that screen readers and search mishandle. About 2-4 days.
- **B. Canvas image editor** (Canva style): weeks. Cards are drawn server-side
  in Python so drafts generate without a browser; a true WYSIWYG means two
  renderers kept pixel-identical, or moving drawing to the browser and losing
  auto-generation.
- **Middle path for B:** more direct handles on the existing draft preview
  (it already drags the hero crop and the inset) - drag the panel, pick the
  font per draft. Days.

Recommendation: the middle path, after 1 and 2.
