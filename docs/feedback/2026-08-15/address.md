# What Was Addressed — 2026-08-15 Feedback

Written as items ship. The request is `feedback.md`, the reading of the code is
`comprehension.md`, and the evidence for each change is its commit message.

Sequencing came from `comprehension.md`: C4 first and alone, because it depends
on no model call, no prompt rewrite and no answer from the client — and because
it is the one item they can confirm from a screenshot.

---

## C4 — Overlay text in capitals, per Page ✅

**Shipped 2026-08-15.** Bodybuilding Tips N Tricks and Fitness Recipes now draw
their panel in capitals; every other Page is unchanged.

**A drawing setting, not a writing one.** `page_layout.text_uppercase`, applied
by `image.text.cased` at draw time. The hook is stored in the case the writer
produced it in, so the operator still reads and edits normal prose, drafts that
already exist change with the switch and cost nothing to redraw, and the model
cannot drift off an instruction it was never given.

Null tracks `config/layout.yml`, which says no; `false` is a Page that has
decided against capitals and stops following the file. Same three-valued
contract as every other column on that table — the migration
(`517b138512ff`) deliberately backfills nothing.

**Four things that were not obvious:**

- **`normalise` first, then the case.** `_SENTENCE_END` needs two *lowercase*
  letters before the full stop — it is the acronym guard that leaves `U.S.`
  alone — so uppercasing first means `tomb.The` never gains its space and is
  measured and drawn as one token. Pinned by a test.
- **The two renderers do not match highlights the same way.** `text.segment`
  compiles each phrase with `re.IGNORECASE` and keeps the line's own casing, so
  the compositor needs *no* phrase transform: as-written phrases find their runs
  in a shouted panel and come back gold. The browser's `splitOnHighlights` is
  exact, so there the text **and** the phrases are uppercased together — one
  side alone and every highlight silently stops matching. The comprehension note
  predicted this breakage on both sides; only the browser has it.
- **Three renderers, not two.** `layout-editor.tsx` draws its own live preview
  and calls `splitOnHighlights` itself. It is the preview beside the new
  control, so missing it would have made the control look like it did nothing.
- **The old CSS `uppercase` stays gone.** `composed-image.tsx` carried a comment
  where a CSS version used to be, removed because shouting in one renderer made
  the preview disagree with the PNG. The case is applied to the strings for that
  reason: `splitOnHighlights` then segments the same characters the compositor
  segmented.

**Driven in a browser**, not just in tests. Signed in, scoped Settings → Global
to Bodybuilding Tips, flipped **Case → Capitals**, saved, reloaded:

```
control on screen           : Case [ As Written | Capitals ]
editor preview shouted      : true      (highlights survive, in the Page's orange)
saved and read back         : page 4 uppercase=true, overridden includes text_uppercase
History Retraced unaffected : uppercase=false, overridden [panel_opacity, template]
Review /review/44 preview   : "IN 1897, BODYBUILDING PIONEER EUGEN SANDOW…"
                              6 of 6 highlights still coloured
composite via /layout/sample: capitals, highlight spanning the line break, mark intact
```

**The panel does grow, and here is the size of it.** Measured on the three real
Bodybuilding Tips hooks through `POST /layout/sample` — the same `text.plan` the
publish path uses:

| Draft | Hook | As written | Capitals |
|---|---|---|---|
| 44 | 53 words | 8 lines / 390px | 10 lines / 480px |
| 45 | 54 words | 8 lines / 390px | 9 lines / 435px |
| 46 | 52 words | 8 lines / 390px | 11 lines / 525px |

So capitals cost 45–135px of hero on a 1120px card at today's hook lengths.
That is an argument for **C6** rather than against C4: the client's 30-word cap
would give most of it back, and their own example wraps to three lines.

Suite is **364** (was 358).

**What this does not do.** Nothing rewrites an existing composite. A draft
already drawn keeps its stored JPEG until something redraws it — a save, a
rewrite, or a regenerate — and a draft already pushed to Metricool cannot be
redrawn at all (round 2's D6, still open). The Review preview shows the new case
immediately either way, which is the screen the operator works on.

---

## Still open from this round

`F5` (read the prompts the client already wrote in the old tool — do this before
C5–C7), then `C6`/`C7` (the numbers, which have to move in the prompt, the field
description and the validator together), then `C5` (the hero prose). The
questions at the foot of `comprehension.md` are unanswered.
