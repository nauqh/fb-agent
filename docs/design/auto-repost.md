# Design: Automatic save and repost (H2)

- **Status:** proposed, not built
- **Written:** 2026-09-15

## What the client asked

> **Overview page.** The saving and reposting is currently all manual and KC
> doesn't seem to be bothered to use it.
>
> So instead lets automate it so have the option on each individual page
> settings. So you can control at how many likes/engagement it is saved.
>
> Also an option to toggle on and off for automatic reposting. Would have the
> option to control how many days later the system would automatically repost.
> So for example if you choose 1000 likes and 30 days then once a post achieves
> 1000 likes the exact same post is rescheduled for 30 days times... at first
> available slot.

In short: the Overview screen's **Save** and **Repost** buttons are manual and go unused.
Make them automatic, per Page, from Settings:

- **Auto-save** a post once it reaches a number of likes.
- **Auto-repost** it, on a toggle, a number of days later, at the first free
  slot.

"1000 likes, 30 days": a post crosses 1000, and the same post is scheduled again
about a month after it first went out. Nobody presses anything.

## Decisions

| # | Question | Decision |
|---|---|---|
| Q1 | Threshold on reactions or engagement? | **Reactions.** It is the number Facebook shows as likes. Measured, it barely matters: at 1000 it is 30 posts against 35 on engagement. |
| Q2 | N days from when? | **The original publish date.** If that date has already passed, the next free slot from now. |
| Q3 | Can a repost be reposted? | **No.** A post whose caption matches one already saved for the Page is not auto-saved. |
| Q4 | Straight to Metricool, or Review? | **Straight to Metricool**, as asked. This is the first path to an audience that skips Review, and it has been agreed as such. The repost is still visible and cancellable on Schedule weeks before it goes out. |

## What was measured (2026-09-15, read-only, last 30 days)

- **Only History Retraced clears 1000 reactions:** 30 of 243 posts, median
  288, best 7,565. Bodybuilding Tips tops out at 34, Fitness Recipes at 24, six
  Pages return no posts at all.
- **Volume.** At 1000, History Retraced would auto-repost about 30 posts a
  month, roughly one a day against about eight posts a day. At 2000 it is 13, at
  5000 it is 4. The threshold is the client's to set; this is what each number
  means.
- **26 of those 30 can be reposted today.** Their planner originals are in our
  bucket and answer 200. The other 4 are old-app links on `chonkycatlabs.com`
  and are dead. The feedback doc's "History Retraced cannot be auto-reposted
  yet" is out of date.
- **Metricool's stats for Hot Tub Timeout's blog id (6372188) return History
  Retraced's posts**, identical rows, every `postId` prefixed with History
  Retraced's `569035169625026`. Unguarded, auto-save would save History
  Retraced's hits under Hot Tub Timeout and repost them onto the wrong Facebook
  Page. See the guard below; the blog id itself wants checking in Metricool.

## Design

### Trigger: the operator opening the app

Event driven, no cron and no scheduler. **Nothing pushes "a post passed N
reactions"** (checked 2026-09-15): Metricool's webhook events are published,
failed, scheduled, draft, comment, inbox and a daily metrics digest; Facebook's
Page `feed` webhook reports feed items, never a running reaction total, and
would need a Meta app with `pages_manage_metadata` and a public endpoint this
app does not have. So the event is ours.

**`GET /pages` is the event.** `PageScopeProvider` in `(app)/layout.tsx` calls
it on every screen, so it fires whenever the operator opens the app. The route
adds the check as a `BackgroundTasks` task and answers exactly as today.

**Throttled per Page, in memory:** a Page checked in the last 6 hours is
skipped. A module-level `dict[page_id, datetime]`, no column. A restart or a
second worker only means an extra check, which idempotency (below) makes free.

Why this is enough: a repost is scheduled weeks ahead, so a check that runs when
KC next opens the app rather than at 06:00 costs nothing. The ceiling is a Page
nobody opens the app for in **30 days**: posts fall out of Metricool's stats
window and a threshold crossing can be missed. Upgrade path if that happens is a
cron calling the same function.

Locally the same event fires, so it runs against real Pages from a laptop.
`METRICOOL_PUBLISH_AS_DRAFT=true` keeps anything it schedules a planner draft,
which is the same protection manual Publish has.

### Data

Alembic revision, `ADD COLUMN` only, existing rows kept:

**Page**
- `auto_save_min_reactions: int | None`, 1 or more. Null is off.
- `auto_repost_after_days: int | None`, 1 to 90. Null is off. Ignored while
  auto-save is off.

**SavedPost**
- `auto_saved: bool`, default false. Only auto-saved posts are auto-reposted; a
  hand-saved post was kept for reference or Write again, not for reposting.
- `reposted_at: datetime | None`: the claim, see Idempotency.
- `repost_draft_id: int | None`, FK to `draft`: the repost, for the screen to
  link.
- `repost_error: str | None`: why it will never be reposted ("the original
  image has expired"). Set only on a permanent refusal.

No schedule state (ADR-0001). The repost's time lives in the planner; these
columns record decisions: "saved automatically", "reposted", "cannot be".

### The run, per Page with `auto_save_min_reactions` set

1. **Read** `metricool.page_posts(blog_id, 30)`.
2. **Guard:** drop every row whose `postId` does not start with
   `f"{page.facebook_page_id}_"`, and log how many. This is the Hot Tub Timeout
   finding; it costs one string comparison.
3. **Auto-save** each remaining row with `reactions >= threshold` that is not
   already saved (post id, the existing unique constraint) and whose caption
   `repost._match_key` does not match a SavedPost already on the Page (Q3).
   `auto_saved=True`, note `Saved automatically at <n> reactions`.
4. If `auto_repost_after_days` is set, for each SavedPost with `auto_saved`,
   `reposted_at` null and `repost_error` null:
   1. **Claim** it: `UPDATE saved_post SET reposted_at=now WHERE id=? AND
      reposted_at IS NULL`; skip if no row changed.
   2. **Build the Draft** with the existing Repost code, moved out of the route
      into `repost.draft_from_saved(session, page, row)`. The route calls the
      same function. A 409 refusal sets `repost_error`; a 502 (host did not
      answer) clears the claim so tomorrow retries.
   3. **Pick the slot:** first free slot on or after `max(published_at + N
      days, now)`. One planner read per Page covers every target, and each slot
      taken in this run is added to the busy set so two reposts never share
      one.
   4. **Schedule** it through the same normalize + `schedule` path Publish
      uses, record `metricool_post_id`, set `repost_draft_id`.
   5. **No slot, or Metricool refuses:** the Draft stays at `review` with a
      warning saying why, `repost_draft_id` still set. The automation degrades
      to today's manual Repost instead of retrying forever.
5. One Page failing is logged and does not stop the others.

### Code moves

- `schedule.next_slot`: its loop becomes a pure `free_slot(slots, busy,
  start)`. The route calls it with now; the run calls it with the target.
- `routes/drafts.publish_draft`: its normalize + schedule core becomes a
  function the run also calls. **Waits for H1 to commit**, which holds that file.
- `routes/overview.repost_saved`: body moves to `repost.draft_from_saved`.

### Screens

- **Settings, per Page, an Automation pane:** "Save posts at [ ] reactions"
  (blank is off) and "Repost [ ] after [ ] days" (checkbox and number, disabled
  while save is off).
- **Overview, Saved list:** an `Auto` tag, and one line per auto-saved post:
  `Reposting <date>` linking the Draft, or the `repost_error`.

## Tests

Against the SQLite fixture, Metricool faked as `test_publish.py` fakes it.

- A post at the threshold is saved and flagged auto; one below it is not.
- A post already saved by hand is not saved again.
- A row whose `postId` belongs to another Facebook Page is ignored.
- A post whose caption matches an existing saved post is not saved (Q3).
- A repost is scheduled at the first free slot on or after publish + N days.
- A past target takes the next free slot from now.
- Two reposts in one run take two different slots.
- Running twice creates one repost, not two.
- A dead original sets `repost_error` and is not tried again.
- A host that did not answer is retried next run.
- No free slot leaves the Draft at `review` with a warning.
- Auto-repost off saves and schedules nothing.
- A second `GET /pages` inside 6 hours does not check the Page again.
- `GET /pages` answers the same whether the check succeeds or raises.
- `free_slot` keeps `test_schedule.py`'s next-slot tests passing unchanged.

Checks: `uv run pytest -q`, `uv run alembic check`, `npx tsc --noEmit`,
`npx eslint src`, a browser pass over Settings and Overview, and one run by hand
against the local planner in rehearsal mode.

## Out of scope

- Re-reading a saved post's reactions after the 30-day window.
- A second repost of the same post.
- Reposting hand-saved posts.
- A cron. Add one calling the same function if a Page goes unopened for weeks.
- Fixing Hot Tub Timeout's blog id. The guard makes it harmless here; the
  Overview screen shows the same wrong data today.

## Sequencing

1. H1 commits (it holds `models.py` and `routes/drafts.py`).
2. Build this: ~2 days. No deploy config changes.
3. Verified after deploy by opening the app and seeing an auto-saved post on
   Overview and its repost on Schedule.
