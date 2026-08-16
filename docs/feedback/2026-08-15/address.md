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

## C5 — A Page can have its own prompts ✅

**Shipped 2026-08-16.** `api/prompts/pages/<slug>/{system,overlay,image}.txt`
wins over the global file of the same name. Present means used, absent falls
back, and the slug comes from `Page.name` the way the watermark asset path
already does. Two Pages have a directory; the other eight are untouched.

**The bug was one line of prose.** The global `image.txt` opens "You generate
the top hero photograph for a History Retraced Facebook post card", so every
Page was drawn to a history brief — sepia, torchlight, period dress. The old
tool arrives at the same place by a different road, which is worth writing down
because the client believes otherwise: both Pages have `image_gen_system_prompt`
null **and** `brand_key` null, and `legacyBrandKeyForPrompts` resolves null
through `NEUTRAL_PAGE_BRAND_FALLBACK = "hr"` into `HR_IMAGE_GEN_SYSTEM_PROMPT`.
Both tools, same accident.

**Whole files, not fragments.** A per-Page file carrying only the differences
needs a merge rule, and the rule is the part that goes wrong — the old tool has
four prompt columns per row precisely so it can avoid one, then silently falls
back to a default when a column is null. Duplication between the global and the
override shows up in a diff; a merge does not.

**Still files, not a column.** For the reason `writer/prompts.py` has always
given: the old system stored 2,350-char image prompts on three pages of which
2,030 chars were byte-identical, and every copy went stale.

**Three things had to move with it:**

- `DraftContent`'s field descriptions restated the caps — "Under 65 words",
  "5–8 short substrings". Fine while one prompt served every Page; not fine the
  moment Fitness Recipes asks for 35 words and 1–3 highlights, because the model
  then gets two caps in one request and picks. The descriptions now say what
  each field *is*. `validators.py` is still the backstop.
- `hero.generate` took neither a Page nor a layout, so `aspect_ratio_for` was
  using `default_layout.image.width` against a Page-resolved `hero_height_px`.
  It takes both now.
- `GET /prompts` takes `page_id` and returns `overridden` per file; the Prompts
  card scopes to a Page and badges the rows. A Page with its own prompts shown
  the global body unmarked is a window reporting the opposite of what the model
  is sent — which is the state the old tool's Settings tab has been in for six
  weeks, and why the client thinks BBTT has a prompt.

**Fitness Recipes is ported; Bodybuilding Tips is drafted.** FR's file carries
the client's own July wording — the rotating openings, the recipe exception to
"exactly 5 points", "never invent research", "Modern, bright, clean. Never a
historical scene." BBTT had nothing to port, so its three files are built from
FR's shape plus the client's Sandow example. **They need approval before they
generate anything.**

**Both keep our body numbers**, 1,800–1,900 chars over 2–3 paragraphs, not the
July prompt's 800–1,300. `BODY_MIN_CHARS` is 1,500, so porting that number
fails `check()` on every draft and burns both retries. That is C7, and it is
blocked on the client — who has since asked for a third set of numbers.

**Verified against the live database and a running API.** Of ten Pages exactly 4
and 6 resolve to their own files, all three each; page 1 is unchanged on the
globals; `/prompts?page_id=4` returns `overridden=true` on all three with the
first line naming the Page. Suite is **380** (was 364).

**The Prompts card itself has not been driven in a browser** — the API side is
verified end to end, the rendering of the badge and the switcher is not.

---

## Still open from this round

`F5` is **done** (2026-08-16, `old-tool-prompts.md`): Fitness Recipes has a real
prompt to build from, Bodybuilding Tips has none — its rows are History
Retraced's, byte for byte, which is what the client was actually complaining
about.

`C5` is **done** (above). What is left is `C6`/`C7` — the numbers, which have to
move in the prompt, the field description and the validator together. The
descriptions are already out of the way, so the change is now two places rather
than three, and the per-Page prompt files are where it lands.

Both are blocked on a short reply from the client rather than on any reading:
their July prompt and their August message give **different numbers** for the
hook cap (35 vs 30 words) and the first comment (800–1,300 vs ≤1,500 chars),
and BBTT's prompt is our draft awaiting their approval, not their words. The
revised question list is at the foot of `comprehension.md`.
