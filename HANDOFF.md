# Handoff

**Updated:** 2026-08-10 · **Next focus:** authentication on the API, then the Railway deploy

Conventions and integration traps live in `CLAUDE.md`, which loads automatically.
This file is state: what is proven, what is mid-flight, what to do next.

## Where you are

Repo: `D:\Laboratory\fb-agent` — a Python/FastAPI + Next.js rewrite of a Facebook
content agent. The **old** app is `D:\Laboratory\social-agent`: reference only,
still deployed, still the thing publishing History Retraced. Read it for prior
art; never edit it.

Branch `main`, clean except one file (below), **10 commits ahead of origin,
nothing pushed**.

Recent work, newest first — read the commit messages rather than re-deriving the
reasoning, they carry the evidence:

| Commit | What |
|---|---|
| `0c72511` | Review queue grouped by day; "Publish now" wired up |
| `9e33efd` | Schedule tab — Metricool's planner, read live |
| `be21124` | Publish path — Supabase upload → Metricool schedule |
| `ebfbdfa` | Heroes were being generated without the brand style block |
| `02a8b74` | Circular inset — upload, resize, reposition |

**Uncommitted work that is not the media change**: a nav → sidebar refactor
(`components/sidebar.tsx`, `logo.tsx`, `app/icon.svg`, `layout.tsx`, `nav.tsx`
deleted) and `design/`. That is the user's own, in flight. Stage by filename.

## What is actually proven vs merely written

Verified against live services:

- Metricool **reads** work with the existing token — `/admin/simpleProfiles`,
  `/v2/scheduler/posts` (302 posts), and the image normalize endpoint.
- Supabase Storage is now the app's only media backend, exercised for real:
  12 files uploaded through `SupabaseMediaStore`'s own code path, every one
  fetched back over its unauthenticated public URL with matching byte counts,
  and rendered in a browser on the Review screen.
- One real Gemini image call, to confirm the image model accepts a
  `system_instruction`. It does.

**Never run: the Metricool write path.** No draft has a `metricool_post_id`.
`METRICOOL_PUBLISH_AS_DRAFT=true` in `.env`, so the first push lands in the
planner without going to the page. Keep it true until a push has been watched
end to end.

## Media is done. Uncommitted.

Storage moved to Supabase on 2026-08-09, after a `grilling` session that settled
eleven questions. The shape that was actually built is **not** the plan this file
carried before — `MEDIA_BACKEND=local|supabase` was rejected in favour of one
backend, and the publish-time upload was deleted rather than kept.

Nine steps, seven of them done. 260 tests pass, `tsc` clean, eslint unchanged
(the `review-list.tsx:87` error is still the pre-existing one).

- **One store.** `SupabaseMediaStore` is the only implementation in `app/`;
  `LocalMediaStore` moved to `tests/conftest.py` as a fake, which is what keeps
  the suite offline. `MediaStore` grew `read()` and `delete()` so the four call
  sites that reached past it for `store.path()` no longer do.
- **Rows still hold bucket-relative paths.** `Draft` gained three
  `@computed_field` URL properties; the frontend uses those and no longer knows
  what a bucket is.
- **Published drafts are frozen** (`routes/drafts._editable`). PATCH, `/image`,
  inset upload/removal and DELETE all 409. This is load-bearing, not hygiene —
  see below.
- **`api/app/publish/storage.py` is deleted.** Publish hands Metricool
  `media.public_url(draft.composed_image_path)`. There is no `{draft_id}.jpg`
  copy any more, and there must not be one again *unless* the freeze goes: the
  copy existed only because a rebuild renames the composite and deletes the old
  file, which would 404 a post Facebook has not fetched yet.
- **Composites are JPEG**, emitted directly by `compositor.compose` — the old
  flow built a PNG and converted it at publish time, so the big file was paid
  for and thrown away. Each rebuild deletes the composite it supersedes
  (`generate._discard`), by exact path, never a pattern.

Two buckets exist, both public, 10MB cap, `image/png` + `image/jpeg` only.
`supabase/buckets.sql` records them; it was applied through the Storage API
rather than the SQL editor, same rows either way.

| | |
|---|---|
| `fb-agent-media` | production. **Empty.** Nothing has ever been written to it |
| `fb-agent-media-dev` | the laptop's. Holds the 12 migrated files |

`.env` now says `SUPABASE_BUCKET=fb-agent-media-dev`. It said the production
bucket, which would have had a laptop test overwrite a live post's image — the
two databases hand out the same draft ids.

Verified in a browser, not just in tests: the Review screen renders all six
composites from the dev bucket, `896x1120`, zero failed requests.

## The next task

**The API has no authentication and no CORS middleware.** Grepped and confirmed
empty. Every route is unauthenticated, including the ones that spend money
(`POST /generate` calls Gemini) and the one that publishes to a real Facebook
page. The database being locked down does not help: requests arrive *through*
the API, which holds the `postgres` credential. A shared-secret header is about
twenty lines and is the last thing standing between this and a public Railway
domain. `METRICOOL_PUBLISH_AS_DRAFT=true` is the only thing currently stopping a
stranger's request from reaching a page.

Then the deploy itself: root directory `api`, start command
`uvicorn app.main:app --host 0.0.0.0 --port $PORT`, **one replica**
(`generate.sweep_stranded` assumes a single writer), and the same `.env` values —
`DATABASE_URL` on the session pooler, `SUPABASE_BUCKET=fb-agent-media`.

## Done on 2026-08-10 — the database moved

**Supabase Postgres, session pooler on `:5432`.** 2 pages / 954 source items /
6 drafts, ids and their gaps preserved, sequences resynced to 3 / 955 / 15.
Verified in a browser: Review renders all six composites from the production
bucket, zero broken images, zero console errors.

Three things that were not obvious:

- **The old rows stored enum *names*** (`COMPETITOR_POST`); `_stored_enum` uses
  `values_callable`, so Postgres stores *values* (`competitor_post`). Reading the
  old file through the new mapping raised `LookupError` before a row copied. The
  migration lowercased a copy of the file, asserting first that every stored
  token really was its own member name.
- **`sa_type=String` looked correct and was not.** 264 tests passed while a
  stored `SourceKind` loaded back as a bare `str`, so `kind.is_factual` — asked
  on every generate run — would have raised `AttributeError` in production. The
  suite missed it because tests *construct* rows rather than reload them. Fixed
  with `SAEnum(native_enum=False, length=32)`; the regression test reloads.
- **RLS was already on** all three tables with zero policies, so `anon` is
  denied everything despite Supabase's default grants. The app is unaffected: it
  connects as `postgres`, which owns the tables and has `BYPASSRLS`. Left as-is
  by decision. `relforcerowsecurity` must stay `false` — forcing it would lock
  out our own API.

**Alembic is in**, adopted the same day, after being declined at the migration
itself. `db.init_db()` is now `alembic upgrade head` rather than `create_all`,
run in-process at startup — one replica, so nothing races for the lock and a
deploy cannot forget its own migration. The baseline was autogenerated against a
throwaway SQLite file and the live database `stamp`ed at it, because autogenerate
against Supabase produced an empty diff. `uv run alembic check` says "No new
upgrade operations detected"; run it before every deploy, since the test suite
builds its schema from the models and so can never catch a missing revision.

The enum columns stay `VARCHAR` (`_stored_enum`). Alembic makes `ALTER TYPE`
writable, but a new enum member is a fact about the Python class and does not
need to be a schema change too.

SQLite is gone from the application entirely. `app/db.py` refuses a non-Postgres
URL. The suite still uses a throwaway SQLite file, but `tests/conftest.py` builds
that engine itself and assigns `db._engine`, so it is not a configuration the app
supports. The pre-migration `fb_agent.db` was moved out of the repo into the
session scratchpad, not deleted.

**The production bucket is seeded**: 13 objects, all verified by unauthenticated
public fetch against byte counts, nothing deleted from `fb-agent-media-dev`.
`SUPABASE_BUCKET=fb-agent-media` in `.env`.

**There is no sandbox any more.** One database and one bucket means a local
Generate writes production rows and production objects. Only
`METRICOOL_PUBLISH_AS_DRAFT=true` keeps output off a real page.

`seed_media_bucket.py` rewrites **no rows**. A stored path is `<yyyy-mm>/<name>`
and means the same thing in either bucket, which is the whole reason rows hold a
path rather than a URL — the same database works against whichever bucket
`SUPABASE_BUCKET` names. It reads, writes, verifies against the destination's
*public* URL unauthenticated (checking byte counts, not just status), and never
deletes from the source. Idempotent via `x-upsert`.

**`api/media/` is gone, deleted by the user on 2026-08-09, and the local-disk
machinery went with it** — the `/media` mount, `media_root`, the `mkdir`, the
`/health` field, the `.gitignore` line. `/health` reports `media_bucket` now.
The earlier `migrate_media_to_supabase.py` was deleted with them: it read local
disk, and there is no longer any local disk to read.

`fb-agent-media-dev` was the only copy of six paid Gemini heroes, which cannot
be regenerated identically. It is no longer: they are in `fb-agent-media` too,
byte-verified. Keep the dev bucket as the backup — nothing writes to it now.

Measured numbers, so they don't get re-litigated:

```
local read   :    3 ms      remote write : 1198 ms    (laptop → Supabase, 1MB hero)
remote read  : 1394 ms      composite    : 1.21MB PNG / 0.27MB JPEG q92
api/media/   : was 44MB from 7 drafts ≈ 5MB each, nothing ever deleted
in the bucket: 12 objects, 17.0MB, 6 drafts (draft 9 is FAILED and has none)
```

The latency figures are laptop-to-cloud. On a server co-located with the bucket
they should collapse to tens of ms — expected, **not** measured.

## Things that will bite you

The Metricool and timezone traps have moved to `CLAUDE.md`, which loads every
session. What remains here is state.

- The DB was migrated **by hand** with `ALTER TABLE ADD COLUMN` (project
  convention is delete-and-reseed; the user's drafts were worth keeping). Draft
  now carries `inset_image_path`, `inset_size_px`, `inset_x_ratio`,
  `inset_y_ratio`, `metricool_post_id`. A fresh clone gets these from
  `create_all`.
- Pre-existing lint error at `web/src/components/review-list.tsx:87`
  (`set-state-in-effect`) — not yours, leave it.
- Known unfixed: `sm:max-w-sm` in `web/src/components/ui/dialog.tsx` makes the
  image lightbox render 384px instead of its requested 1100px. One-word fix,
  never approved.

## Suggested skills

- **`wizard`** — for the deploy step. Choosing a host, provisioning the bucket in
  the right region, and the Supabase-Postgres-vs-volume decision all involve
  dashboard work only the user can do.
- **`tdd`** — the storage seam is a clean fit: the Protocol change and
  `SupabaseMediaStore` are testable with `httpx.MockTransport`, exactly as
  `api/tests/test_publish.py` already does.
- **`grilling`** — before committing to a deployment shape. The database question
  deserves stress-testing more than the media one does.
- **`code-review`** — the five commits above have not been reviewed.
