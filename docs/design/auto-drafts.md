# PRD: Morning auto-drafts

- **Status:** proposed, not built
- **Written:** 2026-09-14

## Problem Statement

Every Draft today starts with the operator, one Page at a time. They switch to
a Page, open Sources, browse that Page's competitor grid and RSS feeds, tick
items into the Cart and press Generate - the Cart generates for the Page they
are on - then wait a couple of minutes before there is anything to review. Then
they switch to the next Page and do it again. With ten Pages that is the bulk of
the morning, and it is the least skilled part of the job: the grid already ranks
what is worth writing about, and the operator mostly takes the top of it.

The part that needs a human is judging the result - is this story right for the
Page, is the hook good, is the picture on brand - and that part happens in
Review, which already has everything it needs.

The client asked for automation before (feedback 2026-08-11, F2). It was parked
because it had no trigger ("no cron, no worker") and no policy for keeping a
human in the loop. This PRD supplies both, and keeps the human as the only one
who publishes.

## Solution

Every morning at 06:00 (Asia/Ho_Chi_Minh), before the operator starts, the
app generates Drafts for each Page that has automation switched on. It picks
the sources itself in two steps: the ranking the Sources grid already shows
narrows the Page's unused sources to its top 10, then a model reads those 10
against the Page's own prompt and picks the ones that suit the Page. It fills
that Page's review queue up to a target the operator sets per Page (3 to 5).

When the operator opens Review, the Drafts are already there, written and
illustrated. For each one they:

- **approve** it, which queues it in Metricool at the Page's next free slot;
- **fix** it with the tools Review already has (edit text, rewrite a field,
  redraw or upload a hero, add an inset), then approve;
- **remove** it with Reject or Delete.

Nothing is ever published without the operator. The automation only writes
Drafts.

The queue is topped up, not added to. If yesterday's Drafts are still waiting,
fewer new ones are generated, so an unattended weekend does not pile up unread
Drafts or Gemini spend.

## User Stories

1. As an operator, I want Drafts generated for my Pages before I start work, so that my morning is reviewing rather than browsing and waiting.
2. As an operator, I want the automation to pick sources for me, so that I do not have to browse the competitor grid for ten Pages.
3. As an operator, I want the candidates to be the sources the Sources grid ranks highest, so that the model only chooses among stories I would have considered.
4. As an operator, I want every competitor to get a turn before one competitor gets a second candidate, so that one loud publisher does not fill the shortlist.
5. As an operator, I want the automation never to pick a source this Page has already generated from, so that I do not review the same story twice.
6. As an operator, I want a Page with no unused competitor posts to get no automated Drafts, so that an empty or unassigned competitor set shows up as an empty queue rather than as Drafts from somewhere I did not choose.
7. As an operator, I want a model to read the shortlist against the Page's own prompt and pick the stories that fit the Page, so that a history Page is not handed a viral post that has nothing to do with history.
8. As an operator, I want the model allowed to pick fewer than the target when the shortlist is off-theme, so that I get three good Drafts rather than five with two I will reject.
9. As an operator, I want the model to judge fit from the same prompt the writer uses, so that the Page's theme is defined once, in Settings, and not a second time for the picker.
10. As an operator, I want the morning to still produce Drafts when the picking model is unavailable, so that a Gemini outage costs me the theme check, not the whole morning.
11. As a developer, I want the model's picks to be checked against the shortlist, so that an invented or duplicated id can never become a Draft.
12. As an operator, I want to switch automation on or off per Page, so that Pages I am not actively running cost nothing.
13. As an operator, I want to set how many Drafts a Page should have waiting (3 to 5), so that the queue matches how much that Page posts.
14. As an operator, I want the automation to only top the queue up to that number, so that Drafts I have not reviewed yet do not pile up with more on top.
15. As an operator, I want a Page whose queue is already full to be skipped, so that no money is spent on Drafts I have no room for.
16. As an operator, I want automated Drafts to appear in Review exactly like the ones I generate by hand, so that there is one queue and one way of working.
17. As an operator, I want a Draft whose writing failed to show up in Review as failed with the reason, so that I know a source was tried and why it did not work.
18. As an operator, I want a Draft whose picture failed to still arrive with its text, so that I can upload or redraw a hero instead of losing the copy.
19. As an operator, I want to see which source an automated Draft was written from, so that I can judge whether the pick was sensible.
20. As an operator, I want to approve a Draft with one action that queues it at the Page's next free slot, so that I do not pick a time for every post.
21. As an operator, I want that approval to tell me which slot it is using before it commits, so that nothing goes to an audience at a time I did not see.
22. As an operator, I want approving several Drafts for one Page in a row to fill successive slots, so that they do not all land on the same time.
23. As an operator, I want a clear message when a Page has no slots configured or no free slot, so that I know to fix Settings rather than retry.
24. As an operator, I want to edit, rewrite and redraw an automated Draft with the existing Review tools, so that fixing one needs nothing new to learn.
25. As an operator, I want to reject or delete an automated Draft, so that bad picks leave the queue.
26. As an operator, I want a rejected or deleted Draft to make room for a new one the next morning, so that the queue refills itself.
27. As an operator, I want to trigger the morning run by hand, so that I can recover a missed morning or try the feature without waiting a day.
28. As an operator, I want triggering the run twice in a row to create nothing extra, so that an accidental double press, or the scheduler firing twice, costs nothing.
29. As an operator, I want the run to answer immediately and generate in the background, so that whatever triggered it is not left waiting minutes.
30. As an operator, I want automated Drafts to use the Page's own prompts, lengths and layout, so that they match what a hand-run would produce.
31. As an operator, I want the automation not to publish anything by itself, so that a human has seen every post before it reaches an audience.
32. As an operator, I want competitor posts to be fresh when the run picks from them, so that the automation does not write about last week's grid.
33. As an operator, I want a Page whose competitor sync fails to still let the other Pages run, so that one broken source does not cost me every Page's Drafts.
34. As a developer, I want the run to be impossible to fire from my laptop by accident, so that local work never bills Gemini for production Pages.
35. As a developer, I want the schedule defined in one place that is visible in the deploy config, so that the time the run happens is not a mystery.
36. As a developer, I want the endpoint behind the existing API key, so that nobody on the internet can spend the Gemini budget by calling it.
37. As a developer, I want the schedule expressed in UTC with the local time written beside it, so that the 06:00 intent survives anyone reading the cron expression.

## Implementation Decisions

### Trigger

- A **Railway cron service** in the same project as the API. It runs one
  `curl` against the API and exits. No image of our own, no process that stays
  up. Railway's docs describe exactly this use: short tasks that exit, and
  "saving resources between task executions, as opposed to having an in-code
  scheduler run 24/7".
- Schedule `0 23 * * *` UTC, which is **06:00 Asia/Ho_Chi_Minh** (UTC+7, no
  daylight saving, so it never drifts). Railway runs cron in UTC and "does not
  guarantee execution times to the minute", which is fine for a morning batch.
- The cron sends the existing `X-API-Key`. The key middleware already protects
  every path, so the endpoint needs no auth of its own.
- There is no in-process scheduler, no polling loop and no queue. The API
  process does nothing until the cron calls it.
- Railway cron was chosen over Vercel cron: the API is already on Railway, the
  Hobby Vercel plan can fire anywhere within the hour, and Vercel would need a
  Next route plus a second secret to forward the call.
- Local development has no cron, so a laptop cannot start a run by itself. That
  is the whole of the "don't bill from dev" protection; no enable flag is needed.

### Idempotency: top-up, not "add N"

- Cron delivery is at-least-once and best effort (Vercel documents both
  duplicate and missed invocations; Railway does not document retries). The run
  therefore sets a **target state** rather than performing an increment.
- For each Page: `wanted = page.auto_drafts - count(drafts in review or
  generating)`. Only `wanted > 0` generates.
- `generating` must be counted. `start_run` inserts placeholder Drafts before it
  returns, so a second call moments after the first sees them and generates
  nothing. Counting `review` alone would let a double fire double the run.
- There is deliberately **no "already ran today" record**. The Draft rows are
  the state, which is the same "the row is the job record" rule generation
  already follows.
- A missed morning is not caught up automatically. The operator sees an empty
  queue and triggers the run by hand; the top-up rule makes that safe.

### Modules

**SourcePicker** (new, deep). Interface: given a session, a Page and a count,
return up to that many Source Items to generate from. Two steps behind that one
call: a free shortlist, then one model call that chooses from it.

*Step 1, shortlist* - the top **10** unused competitor posts, no model involved.
**Competitor posts only; RSS items are never shortlisted.**

- the competitor ranking, **moved out of the Sources route** into a function
  both the route and the picker call, so the grid and the automation cannot
  disagree about what "best" means. Ranking stays as it is today: inside the
  lookback window anchored to the newest post, reactions order, one round per
  competitor (partitioned on author).
- exclusion of sources **this Page** already has a Draft from. Per Page, not
  global: the competitor pool is shared across Pages, and one story can be right
  for two of them.
- a Page with fewer than 10 unused competitor posts gets a shorter shortlist,
  and a Page with none (nothing assigned, or everything used) gets no Drafts
  that morning. No fallback to RSS: an empty queue is the signal to fix the
  Page's competitor assignments on Settings.
- competitor freshness: if the stored pool is stale by the existing
  `stale_after_hours` rule, sync before shortlisting, reusing the existing sync.
- a sync failure is not fatal: it is logged and the shortlist is built from
  the posts already stored.

*Step 2, choose* - one text call per Page:

- **Input:** the Page's name, the Page's resolved system prompt (the same
  three-tier resolution the writer uses, so the theme lives in one place and a
  Settings edit moves both), the count wanted, and the shortlist as numbered
  entries: competitor name, published date, reactions, and the text trimmed to a fixed length
  (the model is judging fit, not writing, so it does not need a whole article).
- **Output:** a typed list of picks, best first, **0 to count** long, each a
  shortlist id with a one-line reason. The reason is logged with the run.
  Picking fewer than asked is allowed and is the point: an off-theme shortlist
  should produce fewer Drafts, not filler.
- **Validation** as a Pydantic AI output validator raising `ModelRetry`, the
  writer's existing pattern: every id must be on the shortlist, no duplicates,
  no more than the count. Two retries, as the writer.
- **Model:** the text fallback chain from settings. The writer's ladder (step
  down the chain on a transient error, surface a non-transient one) is
  currently bound to the Draft output type; it gets generalised to take the
  output type and instructions, so the picker reuses it rather than copying it.
- **Failure:** if the chain is spent or the model answers something that still
  fails validation, the picker falls back to the first `count` shortlist entries
  in ranking order and logs that it did. A picking outage costs the theme check,
  not the morning.
- An empty shortlist makes no call.
- Every candidate is already a stored Source Item (the competitor sync writes
  them on arrival), so choosing writes nothing new and `start_run` takes them by
  id through the existing `resolve_sources` path.

**AutoRun** (new, deep). Interface: `run(session) -> dict[page_id,
list[draft_id]]`. For every Page with `auto_drafts` set, computes `wanted`,
asks SourcePicker, and calls the existing `generate.start_run` with those
sources and that Page, using the Page's defaults (no post style, generated hero,
Page layout). One Page failing does not stop the others. Returns the placeholder
ids; filling them is the existing `run_drafts`.

**Endpoint** (new). `POST /automation/run`. Calls AutoRun, schedules
`run_drafts` for all returned ids as a background task (same shape as
`POST /generate`), and answers **202** with the ids per Page. An empty result is
still 202: "nothing needed" is a success.

**Page** (modified). One new nullable integer column, `auto_drafts`. Null means
automation is off for the Page. Allowed values 3 to 5; `PATCH /pages/{id}`
rejects anything else with 422. Nullable rather than defaulted to 0, for the
same reason as the writing lengths: null reads unambiguously as "not chosen".
Needs an Alembic revision; `alembic check` must come back clean.

**Settings screen** (modified). One control per Page: off, 3, 4 or 5 Drafts
waiting each morning.

**Review screen, Approve** (modified). An **Approve** action on a Draft that
fetches the Page's next free slot (the existing `GET /schedule/next-slot`),
shows the slot by name in the existing publish confirmation, and publishes at
that time through the existing `POST /drafts/{id}/publish`. This is the drawer's
existing "Next slot" flow promoted to the primary action, not a new API. The
slot is fetched on click, as today, so successive approvals see the planner
including the post just queued and take the next slot.

### Unchanged on purpose

- Generation itself: writer, validators, hero, compositor, warnings, failure
  handling. Automated Drafts go through the same `start_run` and `run_drafts`.
- ADR-0001: no local schedule state. The cron schedule lives in Railway, slots
  stay policy, and the planner stays the only source of truth for what is taken.
- Publishing always requires the operator.

### Docs to update when built

- `design.md`: "No queue, no worker, no Redis, no cron" and the Background work
  section now have an external cron trigger; add `/automation/run` to the HTTP
  surface; add the two modules.
- `data-model.md`: `auto_drafts` on the PAGE entity and in the ERD.
- A short ADR-0004: the trigger is an external cron calling an idempotent
  endpoint, not an in-process scheduler, and why.

## Testing Decisions

A good test here drives the module through its interface against the SQLite
test fixture and asserts **rows and returned ids**, never which internal helper
was called. The writer, hero and media store are faked exactly as
`test_generate.py` already fakes them; no test reaches Gemini or Metricool
over the network.

**SourcePicker**, tested:

- the shortlist is the top 10 unused competitor posts in grid order;
- the shortlist gives every competitor one place before any competitor gets a second;
- skips sources this Page already has a Draft from, but not sources only another Page used;
- never shortlists an RSS item, even when competitor posts run short;
- a Page with no unused competitor posts gets an empty shortlist;
- a failing sync still shortlists the posts already stored;
- returns the sources the model chose, in the model's order;
- the model choosing fewer than the count returns fewer;
- an id not on the shortlist, or a duplicate, is retried, and never returned;
- a model that fails falls back to the top of the shortlist in ranking order;
- an empty shortlist makes no model call.

The model is a `FunctionModel` returning canned picks, passed in the same way
the writer tests pass one (`test_writer.py`), so no test calls Gemini.

Prior art: the ranking tests in `test_sources_routes.py`
(`test_competitor_posts_are_written_on_arrival_and_ranked_by_reactions`,
`test_a_stale_pool_still_ranks_rather_than_answering_empty`); moving the ranking
into a shared function must keep those passing unchanged.

**AutoRun top-up**, tested:

- a Page with `auto_drafts = 5` and 2 Drafts in review gets 3 new placeholders;
- a Page with a full queue gets none;
- a Page with `auto_drafts` null gets none;
- **calling it twice in a row creates no extra Drafts** (placeholders at
  `generating` count toward the target) - this is the double-fire guarantee;
- rejected and deleted Drafts do not count, so they are refilled;
- one Page failing still produces Drafts for the others.

Prior art: `test_generate.py` for the run fixtures and fakes
(`test_a_run_with_no_page_is_refused`, `test_a_restart_sweeps_rows_left_generating`).

Not tested, by decision: the endpoint (a thin wrapper, and the key middleware
has `test_auth.py`), the Settings control, and the Railway cron itself. The cron
is verified once for real after deploy by reading the Railway cron log and
seeing Drafts in Review.

Checks to run when built: `uv run pytest -q`, `uv run alembic check`,
`npx tsc --noEmit`, `npx eslint src`, plus a browser pass over Settings and
Approve per `CLAUDE.md`.

## Out of Scope

- **Auto-publishing.** Nothing reaches Metricool without the operator.
- Storing the model's reason for a pick on the Draft. Logged only; add a column if the operator wants to see it in Review.
- A model reading the whole pool. It only ever sees the 10-item shortlist.
- A classifier for time-sensitive stories (the other half of F2).
- Per-Page run times, or more than one run a day.
- A post style, template, no-image or hero-from-source setting for automated runs. They use the Page's defaults.
- A "made by automation" marker on Drafts, or a separate automated queue.
- Catching up missed mornings automatically.
- Dead man's switch monitoring (Healthchecks.io and similar). Add it if a missed morning goes unnoticed in practice.
- RSS items as a source for automated Drafts. Competitor posts only; RSS stays a hand-picked source through the Cart.
- Tweets as a source. They are pasted by hand and paid per read.
- Bulk approve.

## Further Notes

- **Cost.** Worst case is 10 Pages x 5 Drafts = 50 writer calls and 50 hero
  generations on a morning with every queue empty, plus one picker call per Page
  that needs Drafts (10 at most, each reading a 10-item shortlist). The top-up
  rule makes the normal case the number of Drafts the operator cleared the day
  before.
- **Shortlist size.** 10 is a starting number, not a measured one. If the model
  keeps picking fewer than the target because nothing fits, widen it; if it
  picks well from the first few, it can shrink.
- **Wall time.** At the current `GENERATE_CONCURRENCY` of 3 and roughly two
  minutes per Draft, a 50-Draft morning takes over half an hour. A 06:00 start
  leaves room before the operator arrives. Raising concurrency needs backoff in
  the writer's fallback chain first (`design.md`).
- **Slot collisions.** Two approvals for the same Page pressed at the same
  moment can both be offered the same slot, because each reads the planner
  before either has written. Approvals made one after another are fine. Accepted
  for a single operator.
- **Research this design drew on** (read 2026-09-14):
  [Railway cron jobs](https://docs.railway.com/reference/cron-jobs),
  [Vercel managing cron jobs](https://vercel.com/docs/cron-jobs/manage-cron-jobs)
  (at-least-once delivery, idempotency, no retries),
  [Vercel cron usage and pricing](https://vercel.com/docs/cron-jobs/usage-and-pricing)
  (Hobby: daily, within the hour),
  [Healthchecks.io cron monitoring](https://healthchecks.io/docs/monitoring_cron_jobs/),
  [human-in-the-loop content review patterns](https://www.llmcms.org/guides/top-5-cms-patterns-for-human-in-the-loop-ai-content-review).
