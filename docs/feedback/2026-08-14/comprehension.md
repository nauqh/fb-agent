# Our Comprehension — 2026-08-14 Feedback Analysis

Read against the code, not taken at face value. Every claim below cites the line
it was read from. Nothing here has been shipped; `address.md` gets written when
it is.

The round-1 analysis is `docs/feedback/2026-08-11/comprehension.md` and the
letters mean the same thing.

---

## D3 — Publishing times: confirmed working

> I did create the publishing times in Settings. Seemed to work.

First confirmation from a real operator on anything from round 1. `page_time_slot`
CRUD, the flat daily list, `Asia/Ho_Chi_Minh`. No action.

Worth recording because it is the half of D2/D3 that was never exercised by
anyone but us — the other half, the push itself, is D5 below and it was not fine.

---

## A. Regressions

### A2 — Rewrite reports success and changes nothing on screen

**Confirmed in a browser, 2026-08-14.** Driven at `localhost:3000/review/46`
(Bodybuilding Tips, unpublished), Rewrite pressed on the hook:

```
toast : "New hook."
screen changed : false
db changed     : true
Revert shown   : true
Save enabled   : true
```

Then, on a second pass, the button the operator is left looking at:

```
after rewrite, db : "In 2010, Fitness Volt exposed the biggest mistake in bodybuilding: eat…"
screen still shows: "In 2010, Fitness Volt exposed a massive mistake holding lifters back:…"
clicking Save changes…
Save reverted the rewrite: true
model's hook survived    : false
```

So the sequence a reasonable operator follows — press Rewrite, see nothing
happen, press Save — **deletes the rewrite they just paid for**. The client
pressed the button and reported "nothing changed"; what they were not told is
that the row underneath had changed and one more click would undo it.

**Reloading the page shows the new text** (`fresh load, screen==db: true`).
That is the workaround, and nothing on the screen suggests it.

**The API is correct. The screen is wrong.** `POST /drafts/{id}/regenerate`
(`routes/drafts.py:309-374`) calls the model, writes the field, and for the hook
also rewrites `highlight_phrases` and recomposites the card. The row in the
database really does change, and the response body carries the new draft.

**Root cause — `web/src/components/draft-detail.tsx:141-145`:**

```ts
const editorKey = written ? `draft:${draft.id}` : `pending:${draftId}`;
if (editor.key !== editorKey) {
  setEditor({ key: editorKey, form: written ? toForm(draft) : null });
}
```

The editor re-seeds only when the **key** changes, and the key is the draft's id.
`Regenerate` passes `onDone={refresh}` (`:655`), which re-reads the row into
`draft` — and the key is the same id it was a moment ago, so `form` is never
re-seeded from it. The text box still holds the old hook.

The preview does not save it either: `ComposedImage` takes
`overlayText={form?.hook ?? draft.hook}` (`:353`). Form wins. Both halves of the
screen show the pre-rewrite text while the toast says *"New hook. The card was
redrawn and the highlights are new."* (`:1133-1139`) — and the card genuinely
was redrawn, server-side, where nobody can see it.

That seeding rule is deliberate and its docstring is right about what it is
defending (`:131-138`): the 900ms poll must not overwrite text the operator is
typing. It just has no case for "the server changed this row because we asked it
to."

**It is worse than a no-op.** `dirty` compares the form against the row
(`:150`), so the instant the rewrite lands the draft is marked dirty against text
the operator never edited. A **Revert** button appears (`:750-758`), and
**Save changes** writes the *old* hook back over the new one. The one visible
affordance after pressing Rewrite silently undoes it, and every press costs a
Gemini call that is then discarded.

**Why only the text buttons.** Hero and inset changes land on `draft.hero_image_url`
/ `draft.inset_image_url` (`:355-356`), read straight from the row, so those
already work. Only the three `Rewrite` controls read their result through `form`.

**Fix.** `regenerateField` already returns the updated `Draft`
(`lib/api/drafts.ts:178-183`) and the return value is thrown away. Re-seed the
editor from it instead of calling bare `refresh`. Keep any field the operator has
edited? No — they pressed Rewrite on this field and the others are what the
server just kept verbatim, so the row *is* the truth. Take the whole row.

**Why the suite is green.** 353 API tests over a correct API, and no web test
drives this component. Third time this shape has appeared; `CLAUDE.md` already
says a green suite is not a working screen.

---

## B. Missing controls

### B5 — A prompt box on Rewrite

**Current shape.** `rewrite_prompt` (`writer/agent.py:290-317`) is fixed text:
the original brief, the kept fields verbatim, then *"Rewrite ONLY the {field}.
Produce a genuinely different one — a new angle or a new opening, not a reworded
copy."* There is no channel for an operator instruction, in the API
(`routes/drafts.py:309-313`, one `field` query param) or the UI.

**Why "too short" cannot be fixed by pressing again.** The hook's rules are a
maximum and a prohibition, nothing else: `hook_length` at 65 words and
`hook_has_no_question` (`writer/validators.py:77-86`, wired at
`agent.py:243-249`). No minimum exists anywhere. Every retry is an equally valid
short hook, so the button as built can only re-roll — never steer. The client
worked that out from one press.

**Shape to build.**

1. Optional `instruction: str | None` on the regenerate request, appended to
   `rewrite_prompt` as the operator's own line, clearly labelled as theirs.
2. A textarea under each `Rewrite` control, empty by default. Empty must behave
   exactly as today — the no-argument press is the common case and should stay
   one click.
3. Do **not** turn the instruction into a validator. It is guidance for one
   rewrite, not a brand rule; brand rules are `validators.py` and belong to the
   Page.
4. Do not store it on the Draft. It describes an action, not the post — and a
   stored one would be silently reused by the next press.

Blocked behind A2 in practice: a prompt box on a control that appears to do
nothing is untestable by the client.

---

### B6 — No way to add a Page's logo

Two separate problems behind one sentence. Both must land or the item is not
done.

**1. The upload has no UI.** The server side exists and is finished:
`POST /pages/{id}/watermark` (`routes/pages.py:69-133`, stores to the bucket,
deletes the superseded object), `DELETE /pages/{id}/watermark` (`:135-154`), and
a typed client `uploadWatermark` / `removeWatermark`
(`web/src/lib/api/pages.ts:43-56`). **No screen calls either.**

Settings renders the committed asset only
(`web/src/app/(app)/settings/page.tsx:131-149`) — and reads
`page.watermark_image_path` directly rather than `watermarkUrl(page)`
(`pages.ts:67-70`), which is the helper that prefers an upload. So even after
uploading through the API by hand, this card would still print

> missing — nothing to composite over

for the eight Pages without a committed file. Only `history-retraced` and
`the-fact-feed` have one (`api/assets/watermarks/`).

**2. The artwork in `docs/logos/` is the wrong kind of image.** A watermark here
is **white ink stamped on a photograph** — `models.py:114-118` and `:133-139`
are explicit that the avatar is not a substitute. `docs/logos/` holds brand
logos, and the two the client named are
`docs/logos/bodybuilding-tips.png` and `docs/logos/fitness-recipes.jpg`. A JPEG
has no alpha at all, so uploading it composites a coloured rectangle over the
hero. The client's word for the current state — *"no **correct** watermark"* —
is the accurate one.

So B6 needs an upload control **and** a white-ink transparent PNG per Page. The
second is the client's to supply or a designer's to make; we should ask rather
than upload the JPEG and call the item done.

**The failure mode is at least loud.** `compositor._watermark`
(`image/compositor.py:135-170`) raises when a configured mark will not load, so
a bad upload fails the draft with the filename in the message. That is the one
thing the old system got wrong — it swallowed the miss and printed the page name
as text for months.

**Not a blocker for F4 technically**, only in the client's sequencing.

---

## D. Publishing

### D5 — Draft mode, and the app never said so

**The flag.** `settings.metricool_publish_as_draft` defaults to `True`
(`settings.py:340-348`) and goes straight into the payload as
`"draft": settings.metricool_publish_as_draft` (`publish/metricool.py:145`).
Railway was never flipped — noted at the bottom of round 1's `address.md` and
not acted on.

**The real defect is the silence.** Grepping `web/src` and the API for any
mention of draft/rehearsal mode returns the flag's own two definitions and
nothing else. The publish dialog, the toast, the draft row and the schedule
screen all report a scheduled post. Nothing anywhere distinguishes *pushed to a
planner as a draft* from *queued to go out to an audience*. The client was told
their posts were scheduled, and they were not. Reading that as "my bad" is
generous and wrong.

**Two changes, not one:**

1. Set `METRICOOL_PUBLISH_AS_DRAFT=false` on Railway. Restart the service —
   `--reload` watches `.py`, not `.env`, and the same is true of a deploy that
   only changes a variable.
2. Surface the mode where the push is confirmed, so the next person to run in
   rehearsal knows they are. Cheapest honest version: return the flag on the
   publish response and put the word "draft" in the confirmation when it is on.

**Order matters.** (1) makes every push real, with no undo and an audience —
the exact thing `settings.py:342-348` says to hold until a push has been watched
end to end. Do (2) first, then flip (1) and watch one post through.

### D6 — Editing the image after a post is in Metricool

**Why it is frozen.** `_editable` (`routes/drafts.py:700-730`) refuses any edit
to a draft carrying `metricool_post_id`, and the reason is storage, not policy:
a redraw writes a new composite and **deletes the one it supersedes**, while
Metricool holds a URL that Facebook does not fetch until the post is due, days
later. Editing here would delete the picture out from under a scheduled post,
which then publishes with nothing.

**What the client's report adds.** Metricool's own editor takes text and time but
**not media**. So the escape hatch ADR-0001 assumes — change it in the planner —
does not exist for the image. Answering "edit it in Metricool" would be false.

**The only honest path is recall:** delete the planner post, clear
`metricool_post_id`, unfreeze the draft, edit, push again. That needs work we do
not have:

- No delete or update call exists in `publish/metricool.py`. It has exactly two
  planner calls — list (`:186`) and create (`:269`). A `DELETE /v2/scheduler/posts/{id}`
  has to be **spiked live**; Metricool's documentation has been wrong twice
  already (image re-hosting, `Accept` on GETs).
- `metricool_post_id` is set once and never cleared — the only writes are
  `routes/drafts.py:641` and nothing else in the codebase touches it. Today the
  freeze is a one-way door.
- Worse: `draft.metricool_post_id = post_id or "queued"` (`:641`). When Metricool
  does not name the post in its response, we store the sentinel `"queued"` — which
  freezes the draft with **no id to recall it by**. How often that happens is
  unmeasured and must be checked before promising recall.

**This has already bitten, quietly.** The client deleted the app's pushed posts
and rescheduled duplicates by hand. Our rows still hold the dead ids and are
still frozen, and `routes/schedule.py:245-250` maps planner rows to drafts by
that id — so the duplicates match nothing and the schedule screen shows them as
foreign posts. An "unlink" that clears the id is worth having on its own merit,
before any recall feature, because there is currently no way out of this state
short of SQL.

**Recommendation.** Spike the delete endpoint. If it works, build Recall as one
button in the review drawer, wording it as what it is — the post comes out of the
planner. If it does not, the answer to the client is "delete it in Metricool and
we will unlink it here", and the unlink has to exist for that sentence to be
true.

---

## F. Untried

### F4 — Google Alerts

Nothing in the repo mentions Google Alerts (grep across `docs`, `api`, `web/src`:
no matches). Nothing needs to. An Alert can be delivered as an RSS feed, and an
Alerts RSS URL is a feed like any other in Settings → Feeds; adding one probes it
first, so a URL that does not answer is refused rather than saved.

Two things to tell the client rather than build:

- The RSS URL only exists if the Alert's *Deliver to* is set to **RSS feed**.
  A new Alert defaults to email and has no URL to paste.
- Alerts items are links to other people's articles with their own images. C3
  ("use source picture") is deliberately RSS-only, so the toggle will be
  available here — and pointing it at a news site's photograph puts someone
  else's picture under our watermark. Worth saying out loud before they turn it
  on, since C3's rights note was written about our own feeds.

---

## Sequencing

A2 first, alone: it is a client-visible lie, the fix is small, and B5 cannot be
evaluated by the client until Rewrite visibly does something.

Then D5 (2) — say which mode a push used — then D5 (1), the flip, watched.

Then B6's upload control, with the artwork asked for in parallel since it is not
ours to make.

B5 and D6 after, D6 gated on the live spike.

---

## Questions for the client

1. **B6** — Can they supply the eight watermarks as white-ink transparent PNGs?
   The files in `docs/logos/` are brand logos and one of the two they named is a
   JPEG, which cannot be stamped on a photograph.
2. **D5** — Confirm they want the flip now, i.e. that the next publish goes to a
   live audience with no undo.
3. **D6** — Confirm Metricool truly offers no way to replace the media on a
   scheduled post; ours is a second-hand report and it decides whether we build
   recall.
4. **A2/B5** — Was "too short" about this hook, or should the Page's brief carry
   a minimum hook length? A rule is better than an instruction repeated on every
   post.
