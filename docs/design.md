# Design

How the app is put together. The vocabulary is
[CONTEXT.md](../CONTEXT.md); the tables are
[data-model.md](data-model.md); why the old system was cut this way is
[decisions.md](decisions.md) and the three [ADRs](adr/).

The rule this document is written against: **a module is deep when a lot of
behaviour sits behind a small interface**. The previous system failed not
because it had too much code but because its interfaces were as wide as their
implementations — `facebookGenerateGraph.ts` was 819 lines of orchestration
whose every intermediate state was public to the next node.

## Shape

```
        ┌───────────────────────────────┐
        │  web/   Next.js               │   4 screens, no DB access
        │  Sources · Generate · Review  │   talks only to /api over fetch
        │  Settings                     │
        └───────────────┬───────────────┘
                        │ HTTP + JSON
        ┌───────────────▼───────────────┐
        │  api/   FastAPI               │
        │                               │
        │   routes  ──► generate  ──►   │──► Gemini (text, image)
        │              sources    ──►   │──► Metricool · x.com · RSS
        │              compositor       │
        │              media store  ──► │──► ./media on local disk
        │              db               │
        └───────────────┬───────────────┘
                        │
                 fb_agent.db   SQLite, one file
```

Two processes, one machine. No queue, no worker, no Redis, no cron — see
[decisions.md](decisions.md#cut-with-the-evidence) for why each is absent.

## Layout

```
fb-agent/
├── api/
│   ├── config/layout.yml        the one Composed Image form
│   ├── app/
│   │   ├── main.py              FastAPI app, lifespan, static /media
│   │   ├── settings.py          env + layout.yml → frozen models
│   │   ├── db.py                engine, pragmas, session dependency
│   │   ├── models.py            SQLModel: Page, SourceItem, Draft
│   │   ├── routes/              pages · sources · generate · drafts
│   │   ├── sources/             metricool.py · x.py · rss.py
│   │   ├── writer/              agent.py · prompts.py · validators.py
│   │   ├── image/               hero.py · compositor.py · text.py
│   │   ├── media.py             MediaStore
│   │   └── generate.py          the run
│   ├── assets/fonts/Arial-Bold.ttf
│   └── tests/
├── web/                         Next.js, fresh
└── docs/
```

## The modules

Seven, each stated as its interface. Everything else is implementation.

| Module | Interface | What it hides |
|---|---|---|
| `Source` | `fetch(...) -> list[SourceItem]` | three unrelated protocols |
| `Writer` | `write(page, source) -> DraftContent` | prompt assembly, structured output, brand-rule retries |
| `HeroImage` | `generate(prompt, w, h) -> bytes` | `google-genai`, model id, safety refusals |
| `Compositor` | `compose(hero, text, highlights, watermark) -> bytes` | measurement, wrapping, panel geometry, SVG, rasterisation |
| `MediaStore` | `save(bytes, name) -> url` | where files live and how they become URLs |
| `Metricool` | `pages()`, `rivals(page)`, `rival_posts(page)` | auth, blog-id resolution, lookback windows |
| `GenerateRun` | `run(source_ids, page_ids) -> list[draft_id]` | the whole pipeline |

Persistence is **SQLModel** — the table classes in `models.py` are both the
schema and the API-facing types, so there is no second set of DTOs to keep in
sync. There is no migration tool: `create_all` creates missing tables and never
alters existing ones, so during v1 a schema change means **deleting the db file
and letting it rebuild**. That is the intended workflow while there is one
operator and nothing worth keeping. Alembic arrives with the move to Supabase.

SQLite runs on stock settings — no WAL, no journal tuning. One operator, local
disk, and a write pattern of single-row updates never justified it; WAL is one
line if two processes ever contend badly.

Two pragmas are set on **every** connection, and neither is a performance knob:
`foreign_keys=ON`, which is per-connection and off by default — without it every
foreign key in `models.py` is decorative — and `busy_timeout=5000`, because the
default of 0 fails instantly on a locked database instead of waiting, and the
Phase 1 seed script will run while the dev server is up.

### `Source` — the one real seam

Three adapters behind one interface, which is what makes the seam genuine rather
than hypothetical:

- **`MetricoolRivals`** — `fetchMetricoolCompetitors` + `fetchMetricoolCompetitorPosts`,
  windowed by a lookback in days. Writes rows on arrival.
- **`XTweet`** — `https://api.x.com/2`, one tweet resolved from a pasted URL.
- **`RssFeeds`** — seven curated feeds (Smithsonian, Live Science, Science Daily,
  Atlas Obscura, The History Blog, HistoryExtra, All That's Interesting), 7-day
  window, 50 items.

They converge on one `SourceItem`, and generation never learns which adapter
produced one. It asks `is_factual`, which is a pure function of `kind`
(see [data-model.md](data-model.md#is_factual-is-derived-never-stored)).

The ingest rule — **browsing does not write** — lives here. Tweets and articles
are fetched live and become rows only when ticked into the Cart, so the table
does not fill with hundreds of unread articles.

### `Writer` — validation moves inside the interface

One Pydantic AI agent over `GoogleModel`, returning a typed `DraftContent`
(hook, caption, first comment, overlay text, highlight phrases, hashtags, image
prompt).

The brand rules that `validation.ts:44` computed and then discarded as warnings
become `@agent.output_validator` functions raising `ModelRetry` with the
specific failure: hook ≤65 words, no question mark in the hook, ≤5 recap lines
each opening with an emoji, first comment 2–3 paragraphs, body 1500–2100 chars,
birth/death years present, no meta-phrases. Capped at two retries; the happy
path costs the same one call as today. Whatever still fails after two lands in
`draft.warnings` for the operator.

This is the depth that matters most: callers ask for a draft and get a
brand-compliant draft, or an explanation. They never see a retry.

### `Compositor` — the largest implementation, four arguments

Everything about how the image looks is [`layout.yml`](../api/config/layout.yml)
plus the hero and the text. Ported from the old renderer, which already used
resvg rather than sharp for text (`composite-font.ts:24`) and measured with
`opentype.js` advance widths (`overlay-text-measure.server.ts:19`) — both have
exact Python equivalents reading the same `Arial-Bold.ttf`, so this is a port,
not a rewrite.

Internally it splits into `text.py` (measure → wrap → plan panel height) and
`compositor.py` (SVG → raster → paste). That split is an **internal seam**: its
own tests use it, callers never see it. Text measurement is a pure function and
is tested as one; the composite is tested against golden images.

Two facts the Phase 0 spike established, both easy to get wrong:

- **Kerning is not optional.** `opentype.js` applies it inside
  `getAdvanceWidth`. Without it `AVATAR` measures 10.69px too wide at 36px —
  Arial's AV/VA/AT/TA pairs at −152 units over a 2048 em. A token measured too
  wide wraps early, which changes the line count, which changes the panel
  height. With kerning, `fontTools` matches `opentype.js` to four decimal
  places on every token tried.
- **resvg substitutes silently.** It does not error on an unmatched
  `font-family`; it renders a system face and returns a valid PNG of the wrong
  font, which then disagrees with every width the measurer computed. The family
  must be the TTF's own name-table entry — `font-family="Arial"` with
  `font-weight="bold"`, *not* `"Arial Bold"`. The compositor asserts rendered
  ink width against measured advance so a regression here fails loudly.

**Pixel parity with the old system is not a goal.** One good form, re-curated.

### `MediaStore` — one adapter, on purpose

`save(bytes, name) -> url`, with `LocalMediaStore` writing `./media` and serving
it from FastAPI's static mount.

Normally one adapter means the seam is hypothetical and should not exist. It is
kept here because the second adapter is scheduled rather than imagined:
Metricool's servers fetch the image URL themselves
(`metricoolService.ts:182`), so the v2 push cannot work against local disk and
*will* need Supabase Storage or R2. The seam costs one Protocol and one class.

### `GenerateRun` — what replaced the graph

The old LangGraph had six nodes, linear, zero conditional edges
(`facebookGenerateGraph.ts:742`). Each becomes something smaller or nothing:

| Old node | Becomes |
|---|---|
| `resolvePrompt` | a `Page` row read |
| `loadPosts` | a `SourceItem` row read |
| `summarize` | **deleted** — it already mapped each post to itself without calling a model (`:352`) |
| `writeThreeDrafts` | `Writer.write()` per (source × page) |
| `validateAll` | **absorbed** into `Writer`'s output validators |
| `saveBatch` | one transaction |

An `async def`, roughly forty lines.

## Background work and progress

No queue. The sequence, for each (source × page) pair:

1. `POST /generate` inserts a `draft` row with `status='generating'` and returns
   its id immediately.
2. A FastAPI `BackgroundTask` runs `Writer` → `HeroImage` → `Compositor` →
   `MediaStore`, updating `progress_step` and `progress_pct` on the row as it
   goes.
3. The client polls `GET /drafts/{id}` until `status` leaves `generating`.
4. Failure writes `error` and stops. The row stays, so nothing is lost silently.

The row *is* the job record. That is why `draft` carries progress columns and
why there is no `generation_event` table.

Consequence to accept: a process restart mid-run leaves rows stuck in
`generating`. A startup sweep marks any such row as `error`, since with one
process there is no other writer that could still own it.

## HTTP surface

```
GET    /pages                       one row in v1
GET    /pages/{id}
PATCH  /pages/{id}                  quota, watermark (prompts are files)

GET    /sources/rivals?page_id=     Metricool sync, then rows
GET    /sources/articles            curated feeds, live, unsaved
GET    /sources/tweet?url=          single lookup, live, unsaved
POST   /sources                     persist ticked items → ids

POST   /generate                    {source_item_ids, page_ids} → draft ids
GET    /drafts?status=&page_id=
GET    /drafts/{id}                 poll target
PATCH  /drafts/{id}                 operator edits
POST   /drafts/{id}/approve
POST   /drafts/{id}/reject
POST   /drafts/{id}/regenerate-image

GET    /media/{path}                static
```

`hero_image_path` and `composed_image_path` are stored separately so
regenerating the overlay after an edit does not re-pay for image generation.

## Configuration

Four tiers, and the split is deliberate:

- **[`layout.yml`](../api/config/layout.yml)** — how the image looks. Loaded once
  into a frozen Pydantic model at startup, so a bad value fails the boot, not the
  render. No per-page section, ever.
- **[`prompts/*.txt`](../api/prompts)** — what the model is told. Read on every
  call, so an edit needs no restart. Files rather than columns because they are
  the most-edited thing here and they must be reviewable and revertable
  ([why](data-model.md#prompts-are-files-not-columns)). `{panel_pct}` and
  `{highlight_color}` are substituted from `layout.yml` so a prompt cannot
  contradict the compositor.
- **env** — secrets and model ids. Model ids belong here because they get retired
  upstream without notice; the old repo shipped
  `fix(gemini): replace retired image fallback model`.
- **`page` rows** — identity and publishing policy: name, the two external ids,
  quota, watermark file.

## Frontend

Four screens — Sources, Generate, Review, Settings — in a fresh Next.js app. It
holds no database credentials and no Supabase client; every read is `fetch` to
`/api`. The Cart is client state, a list of ids, and is not persisted.

Server state is polled, not streamed. Polling is what the old system did and it
is enough for a run measured in tens of seconds.

## Testing

Each module is tested through its interface, because that is the same surface
callers use.

- `Source` — three adapters, one contract test, recorded fixtures per protocol.
- `Writer` — a fake model returning canned structured output. The validators are
  pure functions and are tested directly; the retry behaviour is tested by a
  fake that fails once then succeeds.
- `Compositor` — golden images at 896×1120, plus pure-function tests on
  measurement and wrapping.
- `GenerateRun` — fakes for `Writer`, `HeroImage`, `Compositor` and
  `MediaStore`; asserts the rows, the progress transitions, and that a failure
  leaves an `error` rather than a stuck row.
- Routes — FastAPI `TestClient` against a temp SQLite file.

No mocking library reaches past an interface. If a test wants to, the module is
the wrong shape.

## Deliberately absent

BullMQ · Redis · a worker process · cron · LangGraph · Supabase auth · RLS ·
`user_id` · Postiz · Facebook Graph OAuth · `sharp` · the `full_overlay` layout ·
the headline badge · rounded corners · a schedule table · a rivals table.

Each was checked against running code or production data before removal;
[decisions.md](decisions.md#cut-with-the-evidence) records the evidence.

## Deferred to v2

Approve → Metricool push, the calendar that depends on it, and the `MediaStore`
swap to hosted storage. Accepted risk: the riskiest integration ships unproven,
and Composed Images are only ever seen locally in v1.
