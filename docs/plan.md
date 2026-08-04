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
- `web/` scaffold, and the **Settings** screen: identity read-only, `daily_quota`
  editable, prompt files shown for reference (they are edited in an editor).

**Done when:** changing `daily_quota` in the browser survives a restart, and
`/pages` returns exactly one page.

**Status:** backend done. `web/` not started.

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
- **Generate** and **Review** screens, text only, polling `GET /drafts/{id}`.

**Done when:** a cart of three sources yields three drafts, and a deliberately
provoked violation (a hook ending in `?`) is visibly retried and corrected
rather than warned about.

This is the phase that decides whether the rebuild is worth finishing.

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
