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

## 3. AI-assisted Write it yourself

Clarified 2026-10-21: the client meant neither a caption composer nor a canvas
editor. She wants the review drawer's per-field AI help on No source > Write
it yourself, before a draft exists.

- [x] `POST /rewrite?page_id=&field=`: the drawer's rewrite with no draft
      behind it. Saves nothing. An empty field is written from the others.
- [x] The rewrite prompt now shows the field as it stands, so "make it longer"
      has text to lengthen - on the drawer too.
- [x] Write/Rewrite box, gold highlighting and counters on each field, shared
      with the drawer (`components/rewrite-field.tsx`).
- [x] Gold phrases are saved with the manual draft.
- [x] Driven in the browser: hook typed, caption written by the model.

Left out: emoji picker and Unicode bold. Neither was asked for.
