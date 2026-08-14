# What Was Addressed — 2026-08-14 Feedback

Written as items ship. The request is `feedback.md`, the reading of the code is
`comprehension.md`, and the evidence for each change is its commit message.

Sequencing came from `comprehension.md`: A2 first and alone, because it is a
client-visible lie and because B5 cannot be judged by the client until Rewrite
visibly does something. B5 followed immediately — the two are one screen.

---

## A2 — Rewrite now changes the screen ✅

**What the client saw.** The toast said the field had been rewritten and neither
the text box nor the picture moved. What they were not told: the row underneath
*had* changed, and the **Save changes** button that appeared next to it wrote the
old text back over the new one. Every press was a paid Gemini call, discarded by
the only visible affordance after it.

**Cause.** `draft-detail.tsx` re-seeded its editor only when the *key* changed,
and the key is the draft's id. `Regenerate` passed `onDone={refresh}`, which
re-read the row into `draft` under the same id — so `form` kept the pre-rewrite
text, the preview drew `form.hook ?? draft.hook` and drew the old one too, and
`dirty` went true against text nobody had typed.

**Fix.** `regenerateField` already returned the updated row and the return value
was thrown away. It is now handed to `applyRewrite`, which refreshes and re-seeds
the editor from that row — the whole row, since the operator asked for this field
and the server kept the others verbatim. `Field` gained no state; the seeding
rule that protects a typing operator from the 900ms poll is untouched.

**Driven in a browser** at `localhost:3000/review/46`, Bodybuilding Tips:

```
screen before : "In 2010, Fitness Volt exposed a massive mistake holding lifters back…"
screen after  : "Since 2010, Fitness Volt has helped lifters banish painful bloating…"
screen changed     : true
screen == db       : true
Save changes shown : false
Revert shown       : false
```

The card in the preview carries the new hook as well — the composite the server
redrew is what the screen now reloads.

## B5 — A prompt box on Rewrite ✅

**Shape built**, following `comprehension.md`:

- `POST /drafts/{id}/regenerate` takes an optional body `{"instruction": …}`,
  capped at 500 characters. Absent, empty and whitespace all mean the call as it
  was — the unargued press is the common case and stays one click.
- The instruction **replaces** the demand for novelty in `rewrite_prompt` rather
  than joining it. The two contradict each other: *"produce a genuinely
  different one"* answers *this is not the post I want*, while *"too short"*
  answers *this is the post I want, said better*. That contradiction is why
  pressing again could never fix the client's hook — no rule anywhere sets a
  minimum length, so every retry was an equally valid short hook.
- It is **not stored on the Draft and not a validator**. It describes an action,
  not the post; a rule that should hold for every future draft belongs in
  `validators.py`, where the whole Page sees it.
- One always-visible input above each of the three fields, not a control behind
  a toggle. The client asked for a textbox in as many words, and a hidden one
  leaves them pressing the button that did nothing.

Four API tests cover it; the whole suite is **357**.

The instruction survives a press rather than clearing — "make it longer" is
usually said twice, and the box is on screen, so nothing is reused invisibly.

---

## Still open from this round

`B6` (watermark upload — needs the artwork as white-ink transparent PNGs, which
is a question for the client), `D5` (say which mode a push used, then flip the
flag and watch one post), `D6` (gated on a live spike of Metricool's delete),
`F4` (nothing to build).
