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
fails `check()` on every draft and burns both retries. That was C7, since
dropped — the numbers stay as they are.

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

`C5` is **done** (above).

`C5` is **done** (above), and `C6`, `C7` and the buried half of `F5` shipped on
**2026-08-17** — see "Lengths and prompts became settings" below.

`C6` and `C7` were dropped on 2026-08-16 and undropped a day later. The note
written then said what it would cost, and it was right about the shape: *"it
needs the validator and the prompt moved together, per Page."* That is exactly
what was built. The estimate that proved wrong was that this was too much for
what it bought.

**Nothing from this round is open.**

---

## C6 — the scaffolding is gone; the word cap now is too ✅

Dropped 2026-08-16, shipped 2026-08-17. The section below is the state as it
stood while it was dropped, kept because the reasoning in it is what the fix had
to answer; what changed is recorded under "Lengths and prompts became settings".

**Shipped, with C5.** "Straight to the point, no year/event/character
scaffolding." The global `system.txt` did not merely permit that opening, it
*required* it — the Gold Standard structure told the model to name a person and
a year. Fitness Recipes and Bodybuilding Tips have their own `system.txt` now,
carrying the client's own July wording, and neither is forced into it.

**Not built: the cap is not enforced.** `validators.HOOK_MAX_WORDS` stays **65**
and nothing retries a hook for length below that.

**But the prompts already ask for less, and that is not an accident to clean up.**
Porting the client's July prompt carried their own number with it:

| File | Asks for |
|---|---|
| `prompts/system.txt` (the other eight Pages) | under 65 words |
| `prompts/pages/fitness-recipes/system.txt` | 35 words |
| `prompts/pages/bodybuilding-tips-n-tricks/system.txt` | 30 words |

So the two Pages the client complained about *are* being asked for a short hook.
What they are not getting is enforcement: a 50-word hook on Fitness Recipes is
over its prompt's 35 and under the validator's 65, and it will be saved without
a warning.

**That asymmetry is deliberate and worth understanding before anyone "fixes" it.**
The prompt instructs and the validator is a backstop; a backstop set looser than
the instruction costs nothing, because the model is still asked for 35. Tighten
`HOOK_MAX_WORDS` to 30 without making it per-Page and every History Retraced
draft starts failing `check()` and burning both retries — the eight Pages on the
global prompt are still being asked for 65.

So enforcing it is not "change the constant". It is making the cap an argument
`check()` takes per Page, and that is the work that was dropped.

**If it is ever picked up, the number is still unsettled by the client** — their
July prompt says 35, their August message says 30, their example is exactly 30.

**One measurement worth keeping**, from the C4 section above: capitals cost
45–135px of hero on a 1120px card at today's 52–54 word hooks. Shorter hooks buy
that back. The client's own request would have helped the thing they complained
about in C4, which is an argument for revisiting this rather than a reason it
was dropped.

---

## Lengths and prompts became settings — C6, C7, F5 ✅

**Shipped 2026-08-17**, a day after C6 and C7 were dropped as not worth the
change. The note written when they were dropped named the fix correctly — *"it
needs the validator and the prompt moved together, per Page"* — and understated
what else it would unlock.

### The numbers

Five nullable columns on `Page`. **Null means the house number**, so the nine
Pages that asked for nothing are untouched and no default was copied onto them:

| | House | Bodybuilding Tips / Fitness Recipes |
|---|---:|---:|
| Hook, max words | 65 | **30** |
| First comment, chars | 1,500–2,100 | **800–1,500** |
| First comment, paragraphs | 2–3 | **3–4** |

**The prompt states the same numbers the check enforces**, from one `Limits`
value. A rule the model was never told is a retry it cannot act on. The house
numbers are deliberately *not* restated in the prompt — they are already in the
prose, and a second copy is the drift `prompts.py` exists to prevent.

**C7 was genuinely unbuildable by prompt alone, and that is now enforced rather
than remembered.** Their 1,500 ceiling was our floor: every draft fails one end,
burns both retries and the run dies at `Exceeded maximum output retries`. Since
the numbers are the operator's to choose now, `Limits.disagrees()` catches the
unsatisfiable combination and `PATCH /pages/{id}` answers **422** with the
numbers in the message. Verified in a browser: a 1,400 ceiling against the 1,500
floor is refused with *"cannot be both over 1,500 and under 1,400"*.

The number itself was never settled with the client — their July prompt asks for
800–1,300 and their August message for ≤1,500. That is no longer ours to
resolve: it is a box on the Settings screen.

### The prompts

`system.txt`, `overlay.txt` and `image.txt` are editable **per Page**, stored on
the Page row. This reverses the read-only decision in `routes/prompts.py`, and
the reasoning there was right about what it was aimed at. Two things change the
answer rather than weaken it:

- **Only overrides are stored.** Null inherits the file; nothing holds a copy of
  text it did not change. The measured failure was drift *between copies* —
  three pages in the old tool each storing the whole 2,350-character image
  prompt, 2,030 characters byte-identical, going stale — and there are no
  copies here.
- **A file cannot be edited in production at all.** Railway's filesystem is
  ephemeral, so a screen writing `prompts/pages/<slug>/x.txt` would lose the
  edit on the next redeploy, silently, days later.

That second point is the whole of F5's buried half. The client wrote *"Within
the old tool, I did write new prompts already in Setting tab"* — and they had
not; Bodybuilding Tips' four columns were History Retraced's, byte for byte,
unedited since 2026-07-05. They believed for six weeks in prompts that did not
exist. A screen that silently discarded their edits on the next deploy would
have reproduced that exactly.

**The globals stay files, stay in git, stay uneditable from the screen.** Every
Page reads them; a textarea on a shared default is what the drift was.

**Blank clears rather than stores.** An emptied box means "go back to the
inherited prompt". Storing `""` would send the model no system prompt at all —
a Page with no voice, failing in a way that looks like the model misbehaving.

**Each prompt says which of three places its text came from** — `page`,
`file-override`, `global` — not merely that it differs. `overridden` alone
cannot answer what the operator is about to do: editing text that is in fact
inherited creates an override nobody asked for. Measured today: Bible Focus
reads all three globals, Bodybuilding Tips all three from its own files.

**Driven in a browser** on Bodybuilding Tips: 30/800/1,500/3/4 saved and
survived a reload, a stored system prompt saved, persisted and cleared back to
the file, and the Page was left as it was found.

Suite is **430** (was 407). `alembic check`, `tsc` and `eslint src` clean.

### Still theirs to decide

The prompts the two Pages inherit from `prompts/pages/` are **ours**, drafted
for C5 and never approved — Bodybuilding Tips had no prompt in the old tool to
port. They can now be edited on the Settings screen without us, which is the
answer to that, but somebody should tell them the current text is a draft.
