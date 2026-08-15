# Our Comprehension — 2026-08-15 Feedback Analysis

Read against the code, not taken at face value. Every claim cites the line it
was read from. Nothing here has shipped; `address.md` gets written when it does.

Rounds one and two are `docs/feedback/2026-08-11/comprehension.md` and
`docs/feedback/2026-08-14/comprehension.md`, and the letters mean the same
thing.

---

## The root cause: one voice, ten Pages

Read C4–C7 as one item before reading them as four. The client's own diagnosis
is right, and it is more literally right than they know:

**The writer's entire per-Page dimension is one sentence.** `_instructions`
(`writer/agent.py:60-75`) concatenates the global `system.txt`, the global
`overlay.txt`, and:

```python
f"You are writing for the Facebook page {page.name}."
```

That is all a Page contributes to how it is written. `prompts.system_prompt`,
`overlay_prompt` and `image_prompt` (`writer/prompts.py`) take a `Layout` and no
`Page` — there is no signature to pass one through.

**The hero's is zero.** `hero.generate` sends the global `image.txt` as the
system instruction (`image/hero.py:189`) and the draft's own `image_prompt` as
the content (`:193`). Neither knows which Page it is drawing for.

**The rules are module constants.** `HOOK_MAX_WORDS = 65`,
`BODY_MIN_CHARS = 1_500`, `BODY_MAX_CHARS = 2_100`,
`FIRST_COMMENT_PARAGRAPHS = (2, 3)` (`writer/validators.py:19-30`), and
`check()` (`:148`) takes three strings and no Page.

**And each number is written down three times.** The prompt file, the pydantic
field description, and the validator constant all state it independently:

| Rule | `prompts/system.txt` | `DraftContent` | `validators.py` |
|---|---|---|---|
| Hook length | `:14` "Strictly under 65 words" | `agent.py:44` "Under 65 words" | `:19` `HOOK_MAX_WORDS = 65` |
| Body length | `:29` "1,800-1,900 characters; never exceed 2,000" | `agent.py:50` "1800-1900 characters" | `:21-22` `1_500` / `2_100` |
| Paragraphs | `:28` "Exactly 2 or 3 paragraphs" | `agent.py:50-51` "2-3 paragraphs" | `:30` `(2, 3)` |
| Highlights | `overlay.txt:8` "5-8 exact substrings" | `agent.py:55` "5-8 short substrings" | — none |

So "make the first comment shorter for BBTT" is not one edit. Change the prompt
alone and the validator retries the model into the old shape; change the
validator alone and the prompt keeps asking for the old shape. Both failure
modes cost Gemini calls and neither is visible on screen.

That is the actual work in this round. C4 is separate and much smaller — it is
a drawing change, not a writing one.

### Where per-Page settings already live

Two precedents, and they point in opposite directions:

- **`PageLayout` (`models.py:472`) reversed exactly this decision once already,
  deliberately.** `config/layout.yml` said it "has no per-page section and should
  not grow one"; a second Page with an unrelated beat was new evidence, so a
  `page_layout` row now holds a Page's overrides and resolution is
  `{**yaml, **row}` field by field (`layout_for.py`). Null means "track the
  file". There is a Settings editor for it (`web/src/components/layout-editor.tsx`).
- **`writer/prompts.py` argues the other way about prompts, from measured
  evidence.** Prompts were database columns in the old system: all three
  configured pages stored the full 2,350-character image prompt, of which
  **2,030 characters were byte-identical**, and every copy went stale — they
  still described a 75%-height hero and a circular logo after the code had moved
  on. Files diff, review and revert; columns did none of that.

Both are right, and the resolution is that they are about different things. A
**number** (30 words, 1,500 characters) is a per-Page value and belongs in a
row, the way `panel_ratio` does. **Prose** (how a hero should look) is the thing
that rotted as a column and belongs in a file — a per-Page file, if we need one,
not a per-Page textarea.

The client's closing sentence is a request for the textarea, and it needs an
answer either way: see F5.

---

## C. Generation options

### C4 — Overlay text in capitals, per Page

**Nothing implements it, and it was deliberately removed once.** Nothing
uppercases the panel in either renderer. What is there instead is a comment
where it used to be, `web/src/components/composed-image.tsx:261`:

```
// Not `uppercase`: the compositor draws the hook verbatim, and
// shouting it here made the preview disagree with the PNG beside it.
```

That is the whole lesson for this item: caps applied in **one** renderer is a
regression, not a feature. The client is right that there is nowhere to change
it — the setting does not exist, only a preview that once shouted alone.

The codebase does already treat caps as a drawing concern elsewhere:
`compositor._badge` does `label.strip().upper()` (`image/compositor.py:220`), so
the badge's word is stored as typed and drawn in capitals. Same shape, and the
right precedent.

**It is a drawing change, not a writing one, and that is the recommendation.**
Uppercasing at render leaves the stored hook in mixed case, so the operator
still reads and edits normal prose, existing BBTT drafts render in caps with no
regeneration, and the model cannot drift from the setting the way it drifts from
a prompt instruction. Ask the model for capitals instead and every one of those
properties is lost.

**The trap: the gold highlights are substring matches, and the two renderers do
not match the same way.** Checked rather than assumed, and the two halves
disagree:

- **The compositor is case-insensitive.** `text.segment` compiles each phrase
  with `re.IGNORECASE` and keeps the matched text verbatim, so an as-written
  phrase finds its run in a shouted line and the gold comes back in capitals.
  Nothing to do on this side.
- **The browser is exact.** `splitOnHighlights`
  (`web/src/components/composed-image.tsx:406-433`) filters on
  `text.includes(phrase)` and drops anything that does not literally appear.
  Uppercase the panel text there and leave the phrases alone and **every phrase
  silently stops matching** — no error, no gold, a plain white preview beside a
  correct PNG.

So: uppercase the text **and** the phrases in the browser; uppercase only the
text server-side, and say in a comment why the phrases are left alone, because
"the other renderer does it" is exactly the reasoning that would put it back.

Do it in the strings, not in CSS. An `uppercase` class on the preview would look
right and leave `splitOnHighlights` segmenting mixed-case text while the panel
shows capitals — two code paths reasoning about different strings, which is how
`:261` got written in the first place.

**And there is a third renderer.** `layout-editor.tsx` draws its own live
preview and calls `splitOnHighlights` itself (`:409`). It is the one on screen
when the operator flips the switch, so missing it makes the new control look
like it does nothing.

**Three renderers, not one, or a preview lies:**

1. `image/text.plan` — what the compositor wraps and publishes.
2. `web/src/components/composed-image.tsx` — the Review preview, HTML, drawn
   from `form` rather than from the stored PNG.
3. `web/src/components/layout-editor.tsx` — the Settings preview, beside the
   control itself.

All three read `GET /layout`, which is what keeps them agreeing (round 1 fixed a
second copy of `layout.yml` on the web side; do not reintroduce one).

**And the order inside the compositor is load-bearing.** `normalise` first, then
the case: `_SENTENCE_END` requires two *lowercase* letters before the full stop
— it is the acronym guard that leaves `U.S.` alone — so uppercasing first means
`tomb.The` never gains its space and is measured and drawn as one token.

**Where the flag goes.** `page_layout` as a nullable `text_uppercase: bool |
None`, plus the row in `layout_for.as_overrides` and one control in the layout
editor. That is one migration and it matches every other override's contract:
null tracks the file, deleting the row resets the Page.

**Two consequences worth measuring rather than assuming:**

- **Capitals are wider, so the panel gets taller.** The panel is a floor that
  grows to fit (`layout.yml`, `panel.ratio: 0.20`, `max_ratio: 0.85`), so wider
  text means more lines and a shorter hero. The 30-word cap in C6 pulls the
  other way. Net effect unknown — compose one BBTT card both ways and compare
  the plans before promising the client the hero keeps its size.
- **Capital-heavy text is where kerning matters most.** `text.Measurer`
  documents `AVATAR` measuring 10.69px too wide at 36px without kern pairs. We
  do kern, so the composite is right; the browser preview is HTML and does its
  own text layout, so preview-versus-composite line counts may diverge more in
  caps than they do today. Check the two side by side, not just the PNG.

### C5 — Hero style: modern and bright, not sepia

**The first line of the prompt is the answer.** `prompts/image.txt:1`:

> You generate the top hero photograph for a **History Retraced** Facebook post
> card.

Every Page's hero is generated under that instruction, followed by
"Documentary or cinematic historical reenactment photography", "Dramatic but
natural lighting (golden hour, overcast, torchlight)", "One grounded historical
moment", and "period-accurate dress". The client called it sepia; the prompt
calls it golden hour and torchlight. Same picture.

**But fixing `image.txt` alone will not fix it**, and this is the part that will
be missed. The hero prompt has two authors:

1. `image.txt`, sent as the system instruction (`hero.py:189`).
2. The **writer's own** `image_prompt` field, sent as the content (`:193`) —
   written under `system.txt:32-33`, which says to produce a prompt that
   "visually capture[s] the **historical scene**".

So a BBTT hero is asked for a historical scene by the text model and rendered by
an image model told it is making a History Retraced card. Both sentences are
per-Page work.

**`prompts.py` already anticipated this.** The merge of `image_rules.txt` into
`image.txt` was justified because a *shared/per-brand* line could not be drawn
correctly — 7 of the 19 supposedly universal lines were History Retraced's taste
— and the docstring says outright that "the old system proves those are not
universal". Splitting by Page is the split that file's own reasoning supports;
splitting by "style vs card contract" is the one it rejects. A per-Page
`image.txt` should therefore be a **whole file**, not a style fragment appended
to a shared one.

**Do not start from scratch.** F5 — the client has already written this prompt.

### C6 — Hook: straight to the point, ≤30 words

**The scaffolding is a hard rule today.** `system.txt:12`:

> Must include the name and year of the event/person.

That is the line the client is asking to drop, and it is what produces the "In
2010, Fitness Volt exposed…" openings visible in the round-2 evidence. It is
prompt-only — no validator enforces it — so relaxing it for a Page is a prompt
change, not a code change.

**Read the example before writing the replacement.** The client's sample names a
person (Eugen Sandow) and carries **no year**, and it is **exactly 30 words**. So
the ask is not "no names": it is drop the obligation to open with a dated
historical anchor. A per-Page hook rule should permit a name and stop requiring
a date, rather than forbidding both.

**30 words is inside the cap, so nothing blocks it and nothing produces it.**
`hook_length` (`validators.py:77-81`) only fires above 65. This is round 2's B5
lesson repeating: the client's "too short" could not be fixed by pressing
Rewrite again because no minimum existed, and "30 words" will not be honoured by
a prompt sentence alone either. A per-Page `HOOK_MAX_WORDS` of 30 is the honest
version — with the prompt and the field description moved with it, per the table
above.

**A knock-on nobody asked about: 5–8 highlight phrases over a 30-word hook.**
`overlay.txt:8` demands "never fewer than 5" phrases of 1–4 words each. Against
65 words that is a scattering; against 30 it is up to a third of the panel in
gold. The phrase count is per-Page work too, and it is the kind of thing that
will come back as "the gold looks wrong" if it is not decided now.

### C7 — First comment: ≤1,500 characters, 3–4 paragraphs

**This one is currently impossible, not merely unimplemented.** Two blocking
rules, both in `check()`:

- `body_length` (`validators.py:115-120`) retries anything **under 1,500
  characters**. The client's *maximum* is our *minimum*. A 1,400-character BBTT
  body would be sent back to the model with "expand it past 1500", twice, and
  then land as a warning on a draft the client asked to be short.
- `first_comment_paragraphs` (`:107-111`) accepts 2 or 3. The client asked for
  **3–4**. Four fails.

Add the prompt (`system.txt:29`, "1,800-1,900 characters; never exceed 2,000")
and the field description (`agent.py:50`), and a BBTT first comment is being
asked for at 1,800–1,900 characters in 2–3 paragraphs while the client wants
≤1,500 in 3–4. Every part of the stack disagrees with the request in the same
direction.

**"Go straight to the main content" has a second target.** `system.txt:26`
requires birth and death years for every character mentioned, and
`birth_death_years` (`validators.py:124-136`) warns when it finds none. On a
history page that is the product. On a bodybuilding page it means "Eugen Sandow
(1867–1925)" in a post about arm training, and the advisory fires on every post
that names nobody. It is already advisory-only and cannot block a run — but it
will put a warning on essentially every BBTT and FR draft, which trains the
operator to ignore warnings. Per-Page, it should be off.

**The retry economics.** These are `ModelRetry` rules, so a mismatch is not a
cosmetic disagreement: it is up to `MAX_RETRIES = 2` extra Gemini calls per
draft, and `plan.md`'s risk table says a retry rate past ~20% means the rule is
wrong rather than the model. Shipping C7's prompt without C7's numbers would
put BBTT at a 100% retry rate.

---

## F. Needs a decision

### F5 — The prompts the client already wrote, in the old tool

**Read on 2026-08-16 — verbatim in `old-tool-prompts.md`.** Two findings that
change the shape of the round:

- **Fitness Recipes has a real custom prompt.** Writer and overlay both, and
  they are a specification: 35-word hook in capitals, a rotating list of
  openings, 1–3 highlight phrases of 2–8 words, first comment 800–1,300
  characters, hero as "fitness or food or lifestyle magazine". It settles
  several of the questions below without asking them.
- **Bodybuilding Tips has no custom prompt at all.** All four prompt columns are
  **byte-identical to History Retraced's**, diffed with `===`, unchanged since
  2026-07-05 — including "include the name and year of the event/person" and the
  birth/death-year rule. That is not a gap in our port; it is the cause of the
  complaint. Their BBTT drafts follow History Retraced's style because they are
  generated by History Retraced's prompt.

So C5–C7 for BBTT cannot be a port. Nothing exists to port. It has to be
drafted, from FR's prompt as the model and their example as the target, and
confirmed with them before it ships.

**And neither Page has ever had a hero prompt.** Both rows have
`image_gen_system_prompt` null and `brand_key` null; `legacyBrandKeyForPrompts`
resolves null to `"hr"` (`page-brand-context.ts:5`), so both fall through to
`HR_IMAGE_GEN_SYSTEM_PROMPT` — "historical reenactment photography",
"torchlight", "period-accurate dress". C5's sepia is that prompt, reached in
both tools by different routes.

The caution held: everything below "Final post card assembly" in FR's overlay
prompt is the stale geometry `prompts.py` predicted — a 75%-height hero and a
circular logo neither compositor draws. Take the voice and the subject rules;
`layout.yml` and `{panel_pct}` are the geometry here.

**And the request underneath: "if you can/need to update the prompts, please let
me know."** The client is asking whether they can keep editing prompts
themselves. Today they cannot — `routes/prompts.py` is **read-only on purpose**,
and its docstring says why: a textarea would quietly become the place prompts
are edited and undo the reviewability that moving them into git bought.

Three honest answers, and this is the decision to take rather than drift into:

1. **Per-Page prompt files, edited by us.** `api/prompts/<page-slug>/image.txt`
   overriding `api/prompts/image.txt` when present. Keeps every property
   `prompts.py` argues for; the client mails us prompt changes and waits for a
   deploy.
2. **Per-Page prompt rows, edited in Settings.** What the client expects and
   what the old tool did. Reintroduces exactly the drift that was measured, and
   the read-only route was written to prevent — and the BBTT row is now that
   argument made by the client's own data. The textarea did not give them a
   per-Page prompt; it gave them a copy of History Retraced's that they believed
   was theirs, for six weeks, until the drafts came out wrong.
3. **Split by kind.** Numbers in a row (per Page, editable, validated, shared
   with the validators so they cannot contradict); prose in per-Page files. The
   client's four asks are three numbers and one paragraph of style, so this
   covers the round — and it means the client can change "30 words" themselves
   without being able to break the card contract.

(3) is the recommendation. It is the same line `PageLayout` already draws:
`panel_ratio` is editable in Settings, the font family is not, because one is a
value and the other is a way to fail invisibly.

---

## Sequencing

**C4 first, alone.** It is a drawing change with no model call in it, it is the
item the client can confirm in one screenshot, and it does not depend on
reading the old tool's prompts. One migration, two renderers, one control.

**Then F5 — read the old prompts.** ✅ Done 2026-08-16,
`old-tool-prompts.md`. Worth every minute: it turned up a specification for
Fitness Recipes and the absence of one for Bodybuilding Tips, which is a
different job from the one this note originally scoped.

**Then the numbers (C6, C7).** They are one change: a per-Page rule set that
`check()` takes as an argument, with the prompt and the field description
rendered from the same values via the `{token}` substitution `prompts.py`
already does for `{panel_pct}`. The whole point is that the three copies stop
being three.

**Then the prose (C5, C6's voice).** Per-Page prompt files, whole files, seeded
from what F5 turns up.

**Last: regenerate the BBTT drafts the client already has.** None of this
changes an existing row. Any BBTT draft already pushed to Metricool is frozen
(`routes/drafts._editable`) and cannot even be redrawn — round 2's D6, still
open. Count them before promising anything.

---

## Questions for the client

Revised after F5 — four of the seven are now answered by the client's own July
prompts, and three of those turn into a **contradiction to show them** rather
than a question to ask.

1. **C4** — Capitals on the overlay only, or on the caption and first comment
   too? The request says overlay text; confirm, because the caption is not drawn
   on the card and caps in a Facebook caption read differently. *(Still open.
   Note their FR prompt asked the model for capitals and the drafts came out
   mixed — worth telling them why we made it a drawing setting instead.)*
2. **C6 — 30 or 35 words?** Their July prompt says "strictly capped at 35
   words"; the message says 30; their own example is exactly 30. We will build
   whichever they name, per Page.
3. **C7 — 1,500 or 800–1,300 characters?** Same disagreement. Their prompt gives
   a range with a **floor**, which is the better shape — it answers the old Q5
   before it was asked. Confirm 800 as the floor, or name another.
4. **C6** — Is the cap **hard** (retry the model above it) or a target? Hard is
   what we would build; a hard cap means an occasional draft comes back reworded
   rather than long.
5. **BBTT has no prompt of its own** — tell them. They believe they wrote one.
   We will draft it from the FR prompt and their example; they should approve the
   words before it generates anything.
6. Please send the screenshot referenced in the message — the caps example.

**Answered by F5, no longer worth asking:**

- *"Fitness lifestyle magazine" for both Pages?* — Yes. Their own wording is
  "fitness **or food or** lifestyle magazine", written on the *Recipes* page.
- *Birth/death years off?* — Yes. FR's prompt drops the rule entirely.
- *Which Page each prompt belongs to?* — Resolved by `page_id`, not by brand key.
- *How many highlight phrases?* — **1–3, of 2–8 words**, against our 5–8 of 1–4.
  They decided this in July; it is the answer to the "the gold will look wrong"
  risk the C6 note raised.
