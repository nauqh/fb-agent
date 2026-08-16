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

**Fix — the rewrite no longer writes.** The first version re-seeded the editor
from the row the server returned, which worked. The shape that shipped is the
operator's own suggestion and is better: `POST /drafts/{id}/regenerate` saves
nothing and returns a **proposal**, the text lands in the editor, and the
operator presses Save exactly as they do for text they typed.

Three things fall out of it:

- **Undo is Revert**, the button that was already there. The row never moved, so
  there is nothing to restore and no history table to keep. Rewriting was
  otherwise destructive: `setattr` on the row, no revisions anywhere in
  `models.py`, and the superseded composite deleted by `generate._discard`.
- **A rejected rewrite costs nothing** — no row write, no composite rebuild, no
  orphaned PNG.
- **Rewrite stopped force-saving the form.** It used to `PATCH` the whole draft
  first, purely because the server read the kept fields off the row; pressing
  Rewrite on the hook silently committed an unsaved caption. The kept fields are
  sent in the request body now — what the new field must fit is what is on
  screen, not what was last saved.

The trade, stated plainly: the model's output lives in the browser until Save,
so closing the drawer loses a paid call. The dirty state is the signal, the same
as for any typed edit.

**Driven in a browser** at `localhost:3000/review/46`, Bodybuilding Tips:

```
1 screen changed            : true      (was: false)
1 db untouched by rewrite   : true
1 composite untouched       : true
1 Save shown / Revert shown : true / true
2 Revert restores the row   : true
3 db == screen after Save   : true
3 card redrawn on Save      : true
3 phrases saved with hook   : true
3 Save disabled again       : true
```

Step 3 first read as a failure and was not: the check ran one second after the
click, and a save that redraws the card takes about ten — the composite is
rebuilt and re-uploaded before the row settles. Worth knowing before reading a
save as broken again.

The preview needs no server round-trip either: `ComposedImage` is an `<img>` of
the hero with the text drawn over it in HTML, from `form`. The stored PNG is
rebuilt by `PATCH` on save, because `hook` and `highlight_phrases` are both in
`DRAWN_FIELDS`.

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

API tests cover the proposal shape and the instruction; the whole suite is
**358**.

The instruction survives a press rather than clearing — "make it longer" is
usually said twice, and the box is on screen, so nothing is reused invisibly.

---

## D5 — Rehearsal mode is off in production ✅

**The operator set `METRICOOL_PUBLISH_AS_DRAFT=false` on Railway.** Verified
against the planner on 2026-08-16 rather than taken on trust — the five drafts
pushed on 08-14 (48, 53, 54, 55, 57) come back `draft=false status=PUBLISHED`,
published to Facebook on 08-15. Across a ±45-day window History Retraced has
338 rows, 331 of them not-draft.

The local `.env` is still `true` and stays that way. It is the rehearsal
environment; nothing run from a laptop should be able to reach an audience.

**Two things the same read turned up.**

*Seven posts are stranded.* `361373471`, `361375892`, `361378352`, `361381672`,
`361383660`, `361386518`, `361389421` — pushed 08-12 under the old flag,
`draft=true status=PENDING`, publication dates on 08-13 and so three days past.
They are the entire draft half of that 7/331 split and they will never go out.
Our app cannot clear them: there is no delete or update call in
`publish/metricool.py`, which is D6. Someone has to delete or re-date them in
Metricool's own planner.

**Superseded 2026-08-17.** D6 shipped, so the app clears them itself. Two are
already gone; the remaining five are two clicks each. See the D6 section below.

*The Review queue was calling published posts "Pending review".* Fixed in
`review-list.tsx` — `metricool_post_id` now outranks `status` on the badge,
which reads **In Metricool**. Not "Published": a post id means handed over, and
those seven prove handed-over is not published. The Schedule screen reads the
planner and is the only screen that can say which.

**What is left of the silence.** The publish confirmation still does not name
the mode. It matters less now that production is correct and the badge is
honest, but a laptop push lands as a draft and says the same thing a real one
does. Small, and worth doing next time this file is open.

---

## D6 — a scheduled post can be changed again ✅

**Shipped 2026-08-17.** `update`, `delete` and `get_post` in
`publish/metricool.py`; `POST /drafts/{id}/reschedule` and
`/unschedule`; and in the drawer, the sentence "In Metricool — change it in the
planner" replaced by **Move** and **Remove from Metricool**.

**Metricool has no in-place update, and nothing said so.** Spiked against the
live planner because the docs have already been wrong twice on this project.
One variable at a time:

| PUT body | outcome | id |
|---|---|---|
| with `id` | old deleted, new created | **changes** |
| without `id` | old survives, second post created | **changes** |

The id moves on every edit. That is the whole design constraint: it is not a
stable handle, so `update` returns the new id and the caller must write it down.

**The old app gets both halves of this wrong**, which is worth telling the
client rather than leaving them to find. It sends no `id`
(`metricoolService.ts:622` builds one body for POST and PUT alike) and then
discards the response (`facebookPublishService.ts:293`). So every edit made in
the old tool leaves a **duplicate** in the planner and the row goes on pointing
at the id its own edit deleted. Their planner may hold duplicates they never
made deliberately.

**DELETE is clean.** 200 `{"data":true}`, confirmed gone by re-reading the
planner, and 404 on a repeat — so treating 404 as success is right and a retry
is safe. The 404 body is **XML** despite being tagged `JsonErrorMessage`;
nothing may call `.json()` on the failure path.

**A text edit reads the post's time before sending it.** `build_body` with no
`when` means `publication_date(None)` — two minutes from now. Without the read,
fixing a typo would silently reschedule the post to immediately. Read from the
planner rather than stored locally, per ADR-0001.

**The picture is still frozen, and that half of the client's ask is not
granted.** Metricool stores a link and Facebook fetches it when the post is due;
`build_image` deletes the composite it supersedes (`generate.py:337`), and that
deletion's own safety comment names this freeze as the reason it is allowed.
So drawn fields are refused while a draft is scheduled, and **Unschedule** is
the way through — it removes the post from the planner *before* anything can
delete the file it was pointing at. Pinned by
`test_unscheduling_lets_the_picture_be_redrawn_again`.

Unschedule keeps the draft rather than deleting it. The complaint was that a
mistake could not be taken back, not that the work should be lost.

**Delete-then-schedule was rejected.** Between the two calls the post does not
exist, and a failure in the second loses it outright. One PUT has no such
window.

**Driven in a browser** on draft 38, against the live planner: caption edit
`362765666 → 362766020`, Move `→ 362766068`, Remove `→ id null` with Publish
offered again and the caption intact. Four mutating requests, all 200.

Suite is **407** (was 391). `alembic check`, `tsc`, `eslint src` and
`next build` all clean.

**Two of the seven stranded posts are gone** as a side effect: `361373471`
(the delete spike) and `361375892` (draft 38's, through the new Unschedule).
Both drafts are back in the queue. Five remain — `361378352`, `361381672`,
`361383660`, `361386518`, `361389421` — and Unschedule now clears them in two
clicks each, whenever the operator wants.

**What this does not do:** replace the image with an uploaded file. The client
asked for that too ("upload a new image — not re-generate or change inset pic").
It needs the composite lifecycle reordered so the old file survives until
Metricool confirms the new one, and it is a bigger change than the three that
shipped. Unschedule → edit → publish is the route to it today.

---

## Still open from this round

`B6` (watermark upload — needs the artwork as white-ink transparent PNGs, which
is a question for the client), `F4` (nothing to build — and no longer blocked,
since the client confirmed B6 done).
