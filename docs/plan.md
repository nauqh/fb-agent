# Build plan

Seven phases. Architecture is [design.md](design.md); tables are
[data-model.md](data-model.md); rationale is [decisions.md](decisions.md).

Two rules govern the order:

1. **The unknown goes first.** The only genuinely unproven piece is the Python
   text renderer. It is spiked in Phase 0, before anything is built on it.
2. **Text before pixels.** Phase 3 produces real drafts with no images at all.
   The prompts are the product; if they are wrong, that is worth knowing before
   a week goes into the compositor.

Every phase ends with something demonstrable in a browser. No phase is "wire up
the plumbing."

---

## Phase 0 — Skeleton, and the one spike

**Goal:** the app boots, and the riskiest assumption is proven or dead.

- `git init`. `uv init api/`, add `fastapi[standard]`, `sqlmodel`, `pydantic-ai`,
  `google-genai`, `resvg-py`, `fonttools`, `pillow`, `httpx`, `pyyaml`.
- `models.py`: the three SQLModel tables from
  [data-model.md](data-model.md), up front. `db.py`: engine, per-connection
  pragmas, `create_all`, session dependency.
- `settings.py`: `layout.yml` → frozen Pydantic model at startup; env for
  secrets and `GEMINI_TEXT_MODEL` / `GEMINI_IMAGE_MODEL`.
- `GET /health` returns db + config state.

**The spike — `resvg-py` on Windows.** Render one line of text from
`Arial-Bold.ttf` and measure a token with `fontTools`. Compare the advance width
against what `opentype.js` produces for the same string in the old repo.

> `resvg-py` is at **0.3.3** — pre-1.0, thin usage. This is the plan's single
> largest technical risk. Kill criteria: it cannot load a local TTF, it cannot
> run on Windows, or measured widths diverge from `opentype.js` by more than a
> pixel or two per token.
>
> Fallbacks, in order: shell out to the `resvg` binary; `cairosvg`; render text
> with Pillow's `ImageDraw` + `fontTools` metrics and skip SVG entirely.

**Done when:** `uv run fastapi dev` serves `/health`, and a PNG of correctly
measured text exists on disk.

### Outcome — passed, with two traps found

`resvg-py` 0.3.3 loads a local TTF on Windows and rasterises correctly. Phase 4
stands as designed; no fallback needed. `fontTools` reproduces `opentype.js` to
four decimal places on every token tried — **once kerning is applied**. Both
traps are written up in [design.md](design.md#compositor--the-largest-implementation-four-arguments):
kerning is mandatory, and resvg substitutes a system font silently when the
`font-family` does not match the TTF's name table (`Arial` + `bold`, not
`Arial Bold`).

`tests/spike_text_render.py` keeps both checks runnable.

---

## Phase 1 — Pages and Settings

**Goal:** the one Page — History Retraced — exists as a row, with its prompts on
disk, visible in a browser.

- `page` table, seeded by `scripts/seed_page.py`: four constants, read from the
  old template row and cross-checked live against Metricool. Nothing else is
  migrated ([why](data-model.md#layout-is-config-not-data)), and the app no
  longer talks to Supabase at all.
- Prompts extracted to `api/prompts/*.txt`
  ([why](data-model.md#prompts-are-files-not-columns)), with `{panel_pct}` and
  `{highlight_color}` substituted from `layout.yml` so a prompt cannot disagree
  with the compositor.
- `GET /pages`, `GET /pages/{id}`, `PATCH /pages/{id}`.
- `web/` scaffold, and the **Settings** screen: identity and watermark shown
  read-only, prompt files shown for reference (they are edited in an editor).

**Done when:** `/pages` returns exactly one page and the Settings screen renders
it. The screen shipped with an editable `daily_quota`; the Quota was cut
entirely on 2026-08-06, and Settings is read-only throughout as a result.

**Status:** done. Backend, and `web/` on the real API — `GET /prompts` was
added so Settings reads the files rather than a bundled copy, which had already
drifted to a file that no longer existed.

`getQuotaUsage` was the one thing left on the fixture store, counting approved
Drafts until `GET /drafts` arrived in Phase 3. It never made that move — the
Quota was cut on 2026-08-06 and the function went with it, so nothing in `web/`
reads a fixture any more.

---

## Phase 2 — Sources and the Cart

**Goal:** browse all three source kinds, tick items, see rows appear.

- `source_item` table with `UNIQUE (kind, external_id)`.
- `sources/metricool.py` — competitors and their posts, per page, lookback-windowed.
  Writes on arrival.
- `sources/rss.py` — the Page's curated feeds, from `config/sources.yml`.
- `sources/x.py` — one tweet from a pasted URL via `api.x.com/2`.
- `GET /sources/competitors|rss|tweet`, `POST /sources`.
- **Sources** screen: three tabs, the Cart as client-side ids.

**Enforce here, not later:** browsing does not write. RSS items and tweets become
rows only on `POST /sources`. Competitor posts are the exception.

**Done when:** ticking one item of each kind produces exactly three rows with
the right `kind`, `author`, and `synced_for_page_id`; re-ticking produces none.

### Outcome — passed, with three vendor traps found

Verified against the live APIs, not fixtures: 22 competitors and 500 posts for
History Retraced, all seven feeds answering, 50 RSS items, 0 failures.

- **Metricool's `creationDate.dateTime` is naive local time in the account's own
  zone** — Europe/Madrid here, whatever the `timezone` parameter says. Read as
  UTC it puts every competitor post two hours out, which is invisible until the grid
  sorts wrongly. `created` is epoch ms; use that.
- **Feed `<title>`s read badly as a byline** — "History | smithsonianmag.com",
  "Archaeology News -- ScienceDaily". `author` is what the card shows and what
  reaches the writer, so publishers are named beside the URL in `CURATED_FEEDS`.
- **x.com answers 200 with an `errors` array** for a deleted or missing tweet,
  so the status alone does not tell you the read worked.

`POST /sources` refuses an RSS item whose host is not one of the curated feeds'.
The tab is live, so the client posts the item body back rather than an id the
server can look up; without the check the endpoint accepts arbitrary text and
hands it to the writer. This was `isCuratedFeedUrl` in the old repo and it is
the one guard worth carrying over — it is what keeps "fully curated" a property
rather than an intention.

`GET /sources?ids=` was not in the design and had to be added: the Cart holds
ids and something has to turn them back into rows.

**Facebook CDN URLs are signed and expire.** A freshly synced competitor post's
`oe` parameter is about four days out, while the window is seven, so an
`image_url` frozen at first sync dies while the post is still on screen. Proven,
not inferred: four production rows from the old system, synced 2026-07-27 with
`oe` of 2026-07-31, all return **403** today — every competitor image in the old
app is currently broken, and it renders them with no `onError`.

`_upsert` therefore refreshes `image_url` and the three metrics on a competitor
sync, and only there. `text` stays frozen: the metrics and the CDN URL are the
vendor's, the words are what the operator chose, and a Draft's provenance must
not drift. `POST /sources` refreshes nothing — the client is handing back a body
it was shown, not a fresh read, so it must not be able to rewrite a row.

Commit `db1dfba` recorded it as unknown whether Metricool re-signs or serves a
stale URL of its own. **It re-signs.** Back-to-back calls return byte-identical
URLs, which is what made the first check inconclusive, but a sync today returned
`oe` four days in the future while rows untouched since July hold a July `oe`.
Refreshing on sync is therefore sufficient for the grid.

Feeds and windows moved out of `sources/rss.py` into
[`config/sources.yml`](../api/config/sources.yml), keyed by `page.name`, ahead of
page two — the old repo's own comment predicted this, warning that appending to
one flat list would put hot tub news on a history grid. `article` became `rss`
and `rival_post` became `competitor_post`, the latter because Metricool's API
already says competitor and translating at every boundary buys nothing.

**Status:** done. `web/` Sources is on the real API, proxied by a `next.config`
rewrite so there is no CORS to configure. Generate and Review still read
fixtures until Phase 3.

---

## Phase 3 — Writer, end to end, no images

**Goal:** a real Draft, written by the real agent, reviewed in the browser.

- `writer/agent.py` — one Pydantic AI agent over `GoogleModel`, typed
  `DraftContent` output.
- `writer/prompts.py` — loads `prompts/*.txt` and substitutes the layout tokens
  (already built); add the style-vs-factual instruction, chosen from `kind`.
- `writer/validators.py` — the seven brand rules as `@agent.output_validator`
  raising `ModelRetry`, capped at two retries; residue lands in
  `draft.warnings`.
- `generate.py` — the run. `POST /generate` inserts `status='generating'` rows
  and returns ids; a `BackgroundTask` fills them; progress columns advance.
- **The Cart stops writing. `POST /generate` becomes the only write point** —
  see below. `GET /sources?ids=` and the client's `savedIds` map both go away.
- **Generate** and **Review** screens, text only, polling `GET /drafts/{id}`.

**Done when:** a cart of three sources yields three drafts, and a deliberately
provoked violation (a hook ending in `?`) is visibly retried and corrected
rather than warned about. Ticking ten RSS items, unticking nine and generating
leaves **one** `source_item` row, not ten.

This is the phase that decides whether the rebuild is worth finishing.

### Ticking stops writing

Today a tick on an RSS item or a tweet is a `POST /sources`. Untick only drops
the id from the Cart — there is no `DELETE`, so the row survives with nothing
referencing it. Tick ten, untick nine, generate one, and nine permanent orphans
remain: the junk accumulation "browsing does not write" exists to prevent,
arriving slowly instead of quickly. The comment defending it claimed "a Draft
generated from it points back at it", which is exactly false for the rows that
become orphans.

The deeper fault is that **one gesture means two things**. For a competitor post
the sync owns the row and a tick is a local cart add; for an RSS item the tick
*is* the write. Same checkbox, different semantics, different failure modes.

So the Cart carries the item instead of creating it, and `POST /generate` writes
what it is about to use. Nothing is saved that is not used, and the rule becomes
true as stated rather than nearly true.

Consequences, all of them simplifications: ticking becomes instant and offline,
with no spinner and no failure path; `savedIds` disappears, taking with it the
bug where a ticked item renders unticked after navigating away and back;
`GET /sources?ids=` disappears, because the Cart already holds what it renders;
and the curated-feed guard moves to generate, beside everything else it protects.

The asymmetry stays visible in the type, because it is real: **a body may be
sent only for a kind the client is allowed to create.** RSS items and tweets go
by value and are validated on arrival. Competitor posts go by id — the sync owns
them, and there is no equivalent of `is_curated_url` for a Facebook post, so
accepting a competitor body would accept arbitrary text.

This changes the contract [design.md](design.md#http-surface) records for
`POST /generate`, which is why it is settled here before the code exists. Doing
it now is free; patching it today with a `DELETE /sources/{id}` route, its
foreign-key guard, its tests and its docs would mean building all of that a week
before deleting it.

### But competitor posts stay stored — reversed 2026-08-06

This section used to say the opposite: that once the Cart stopped writing,
competitor posts were the last write-on-browse and should go read-through, with
`POST /generate` re-fetching from Metricool to confirm an `external_id`. That is
withdrawn. **The sync keeps writing them.**

It was withdrawn because it contradicted the section immediately above it, which
had been true all along and was not noticed: *"Competitor posts go by id — the
sync owns them, and there is no equivalent of `is_curated_url` for a Facebook
post."* Going by id **requires the row to exist**. Both paragraphs were written
in the same sitting and cannot both hold.

Removing the storage means removing the check with it, and the replacement is
worse. Confirming a competitor `external_id` would mean a Metricool call at the
front of `POST /generate` — an operation already 60s deep in paid model calls —
against an API that timed out and 502'd twice during Phase 3 alone. A cart of
three competitor posts would fail for a reason having nothing to do with the
posts, the writer, or anything the operator can act on. That is a new failure
mode bought with nothing.

And the rule was being applied past its purpose. "Browsing does not write" exists
to stop the table filling with items nobody looked twice at — the RSS grid is 50
items a refresh, unbounded over a week of idle scrolling. Competitor posts are
not that shape:

- they arrive from a **Sync the operator pressed**, not from a tab opening
  (Phase 2 already made that explicit);
- the set is bounded by the seven-day window, ~500 rows, and does not grow with
  how much anyone browses;
- re-syncing updates the same rows through `VOLATILE` rather than adding new
  ones, which it must, because the CDN URLs expire inside the window.

So it is a sync, not a browse, and the ingest rule keeps one documented
exception. `_upsert`, `VOLATILE` and `synced_for_page_id` all stay.

**Done when:** browsing the RSS and Tweets tabs, in any order, writes zero rows;
the Competitors tab writes only when it syncs.

### Outcome — passed, once the rules stopped fighting the prompt

Both done-when checks hold. Ticking ten RSS items, unticking nine and generating
leaves **one** row. A cart of three sources yields three drafts.

The three-source run failed the first four times it was tried, and every failure
was the same shape: **a rule the prompt never asked for.**

- **The paragraph rule was enforced and never stated.** `validators` demanded
  2–3 paragraphs; nothing in `system.txt` or the output schema mentioned
  paragraphs at all. The model wrote 4–5 and was rejected on the first attempt
  of *every* run. The old repo asked for it three times over
  (`hr-tff.ts:22`, `draft-schema.ts:28`, `facebookGenerateGraph.ts:377`); the
  check was ported and the instruction was not.
- **The length rule disagreed with itself.** The prompt said "ideally between
  1,800 to 1,900 characters max" — read as a preference — while the validator
  hard-failed at 2,100. Bodies came back at 2,325 and 2,117.
- **`birth_death_years` could not be satisfied at all.** Two ways: its regex
  wanted `\d{4}`, so `Wu Zetian (624 – 705 AD)` counted as *no years found* and
  every pre-1000 subject was unwritable on a history page; and a story naming no
  people — an Atlas Obscura piece on the Zantigo taco chain — can never produce
  them. In both cases the writer resubmitted correct text until the retries ran
  out and the run died.

Fixed: the prompt states the paragraph and length rules directly, the regex
takes three-digit years and an AD/BC/BCE/CE suffix, and `birth_death_years`
moved out of `check` into `advise` — a Warning, which is how the old repo had it
(`validation.ts:100`, "may be missing"). Same seven blocking rules afterwards:
**zero retries, and the run went from 352s to 90s.**

The lesson is a constraint on the design, not a one-off fix:

> A validator may **block** only if the prompt states it and the model can
> verify it in its own output. Everything else is a Warning.

That is what separates `check` from `advise`. Moving a rule from warning to
blocker raises the bar on its precision — a loose warning is noise, a loose
blocker is a dead run — and every rule in `check` is now a count the model can
do itself.

Three more traps, found by running it rather than reasoning about it:

- **`gemini-2.0-flash` answers 404 "no longer available"**, and was the last
  link of the fallback chain. It is still returned by `models.list()`, so the
  listing is not evidence — each link is now verified by generating from it. The
  last link is `gemini-flash-latest`, an alias, so it cannot rot the same way.
  Same rot the old repo hit on the image side (`376afdc`).
- **`is_transient` matched `"500"` inside `"1500"`.** With `BODY_MIN_CHARS`
  at 1,500, our own validator message read as an overloaded server, which would
  have moved a run onto a different model for a reason that had nothing to do
  with availability. Codes are now matched as codes.
- **A failed run was given `status='review'`.** Empty rows sat in the queue
  looking ready, their only tell an `error` column nothing rendered — five of
  nine drafts in the local database were failures parked in the review queue.
  `DraftStatus.FAILED` is its own state; approving one is a 409, rejecting it
  still works.

No migration was needed for that: SQLModel stores `status` as a plain
`VARCHAR` with no `CHECK`, so a new enum member is not a schema change.

**Status:** done.

---

## Phase 4 — Images

**Goal:** the Composed Image, at 896×1120.

- `image/hero.py` — `google-genai`, image output, size from `layout.yml`.
- `image/text.py` — measure, wrap, plan panel height. Pure functions, unit
  tested. Panel grows from `ratio` toward `max_ratio`; the font never shrinks.
- `image/compositor.py` — hero + black panel + gold highlights + watermark.
  A configured watermark file that does not load must **raise**; the text
  fallback is only for a Page with no logo at all. The old code returned `null`
  there, which is how History Retraced lost its logo unnoticed for weeks.
- `media.py` — `LocalMediaStore`, static `/media` mount.
- `hero_image_path` and `composed_image_path` stored separately from the start.
- **Download a ticked Source Item's picture into `MediaStore`.** Deferred to
  here because it cannot be finished earlier — see below.

### The competitor image, and why it waits for `MediaStore`

Measured in Phase 2, recorded so it is not re-derived:

- Metricool serves **one** post image and it is a **130×130 thumbnail**
  (467 of 482 posts). No second image, no HD field. The URL signature covers the
  size parameter, so `s480`/`s720`/`p720` and dropping `stp` all return 403.
- A real image exists only on the Facebook post page, as its `og:image` —
  **600×750**, readable without auth on an ordinary User-Agent. But it is one
  page fetch per post: **~54s and ~24 MB for a 60-post grid load**, and 1 in 5
  posts (video, some link posts) carries no `og:image` at all. So it is a
  tick-time operation, never a browse-time one.
- That `og:image` URL is **itself a signed, expiring fbcdn link**. Fetching it
  early and storing the URL therefore buys nothing. Only the *bytes* are
  durable, which is why this needs `MediaStore` and lands here.

The grid needs none of this and is already correct: the sync re-signs every URL
on each read, and the card renders at 64px so a 130px source is not upscaled.
What breaks without the download is a **ticked** post — it falls out of the
7-day sync window, nothing refreshes it, and its picture 403s while attached to
a Draft.

Scraping facebook.com is fragile and arguably against their terms even at one
request per ticked item, so it must fail soft to the 130px thumbnail rather than
fail the tick.

**Done when:** a generated image sits side by side with a real History Retraced
post and the difference is taste, not correctness.

The geometry half of that is already proven: replaying a real post's overlay
text through `layout.yml` reproduces its 6 line breaks word for word, its 45px
line height, its 300px panel and its 820px hero. Keep that post as the golden
fixture rather than inventing one.

---

## Phase 5 — Review actions

**Goal:** the operator loop closes.

- `PATCH /drafts/{id}` for text edits, `POST .../approve`, `.../reject`.
- `POST /drafts/{id}/regenerate-image` — recomposites from the stored hero, so
  an overlay edit does not re-pay for image generation.
- Startup sweep marking stranded `generating` rows as `error`. Safe only because
  there is exactly one writer process — note that in the code.

**Done when:** sources → generate → edit → approve runs unassisted, and killing
the server mid-run leaves an `error` row rather than a stuck one.

---

## Phase 6 — Cutover

**Goal:** stop using the old agent.

- Run both against the same sources for a week. Compare drafts by hand.
- Move History Retraced over. Leave the 464 historical drafts behind — 237 are
  published and Metricool holds that record.
- Old repo goes read-only. It stays deployed until v2 exists, because it is
  still the only thing that can push to Metricool.

**Done when:** a week of posts came from `fb-agent`.

---

## Risks

| Risk | Where it bites | Response |
|---|---|---|
| `resvg-py` 0.3.3 is immature | Phase 4 dead on arrival | Spiked in Phase 0 with three fallbacks |
| Prompts don't survive the port | Phase 3 output is worse than today | Phase 3 is text-only and early; compare against real drafts before building images |
| `ModelRetry` doubles or triples cost | Phase 3 | Cap at 2, log retry rate; if it exceeds ~20% the rule is wrong, not the model |
| Gemini image refusals | Phase 4 | Draft survives with `error` set and hero missing; operator retries |
| No Metricool push in v1 | Phase 6 | The old system stays deployed and publishes |
| x.com API access | Phase 2 | Confirm the credential still works before starting the phase |

## Not in this plan

Metricool push, the calendar, hosted media storage, multi-tenancy, the
`full_overlay` layout, the headline badge, saved viral posts, a scheduler of any
kind. See [decisions.md](decisions.md#deferred-to-v2).
