# Handoff

**Updated:** 2026-08-11 · **Next focus:** the deploy — web on Vercel, API on Railway

Conventions and integration traps live in `CLAUDE.md`, which loads automatically.
This file is state: what is proven, what is mid-flight, what to do next.

## Where you are

Repo: `D:\Laboratory\fb-agent` — a Python/FastAPI + Next.js rewrite of a Facebook
content agent. The **old** app is `D:\Laboratory\social-agent`: reference only,
still deployed, still the thing publishing History Retraced. Read it for prior
art; never edit it.

Branch `main`, clean, and **in sync with origin** — `github.com/nauqh/fb-agent`
is at `bb4c81e`. This is a change from what this file said for a long time
("nothing pushed"); commits reach the remote without anyone running `git push`
in the session, so assume a commit is public the moment it exists.

Recent work, newest first — read the commit messages rather than re-deriving the
reasoning, they carry the evidence:

| Commit | What |
|---|---|
| `bb4c81e` | Sign-in on the web app; `(app)` route group; session cookie |
| `0675c1d` | Publish field seeds on the Page's clock; footer is one strip |
| `b5aa168` | A publication time can be chosen; Schedule screen was on the browser's clock |
| `0c7c7fa` | Feeds for the eight Pages that had none |
| `62586da` | The old app's second card template, with its headline badge |

## What is actually proven vs merely written

Verified against live services:

- Metricool **reads** work with the existing token — `/admin/simpleProfiles`,
  `/v2/scheduler/posts` and the image normalize endpoint. Read across all ten
  Pages on 2026-08-11: **4,975 planner rows**, the largest being History
  Retraced at 2,135; `GYM Motivation` ×2 and `House of Common Sense` return
  zero. Every row was written by the old app.
- The **sign-in** works end to end, driven in a browser: a deep link while
  signed out lands on `/login?next=…`, the wrong pair is refused, the right one
  returns to where it started, `/api/pages` answers 200 with the cookie and 401
  after `POST /auth/logout`. Local dev server only — **not** exercised on a
  deploy, and `proxy.ts` failing to be picked up is silent by design.
- Supabase Storage is now the app's only media backend, exercised for real:
  12 files uploaded through `SupabaseMediaStore`'s own code path, every one
  fetched back over its unauthenticated public URL with matching byte counts,
  and rendered in a browser on the Review screen.
- One real Gemini image call, to confirm the image model accepts a
  `system_instruction`. It does.

**Never run: the Metricool write path.** No draft has a `metricool_post_id`, and
the planner holds **0 rows with `draft: true`** across all ten Pages — measured,
not assumed, so nothing this app sent is sitting there unnoticed.
`METRICOOL_PUBLISH_AS_DRAFT=true` in `.env`, so the first push lands in the
planner without going to the page. Keep it true until a push has been watched
end to end.

Note what that flag does and does not do, because it has been misread: it is a
field on the *planner row*. The post still reaches Metricool. What it stops is
Metricool pushing on to Facebook.

## Sign-in — done 2026-08-11

The web app was open to anyone who found the URL, and it is the thing holding
`API_KEY` (`proxy.ts` attaches it on the caller's behalf), so an open UI was an
open API with extra steps.

One signed cookie, no session store — ADR-0002 left nothing to look a session up
in. `lib/auth.ts` HMACs an expiry with `AUTH_SECRET`; the expiry is inside the
signed payload as well as on the cookie, so editing `Max-Age` in devtools
extends nothing. Web Crypto rather than `node:crypto`, because `proxy.ts` runs
on Edge.

Three things not to rediscover:

- **The routes cannot live under `/api/`** — `next.config.ts` rewrites that
  prefix wholesale to FastAPI, so a handler there is never reached. Hence
  `/auth/login` and `/auth/logout`.
- **`proxy.ts`'s matcher must exclude `_next/static` and `_next/image`.** The
  login page is built from them, so redirecting them serves a page with no
  styles and no bundle.
- **The rail moved into an `(app)` route group.** It lived in the root layout,
  which wraps `/login` too. A group, not a segment — every URL is unchanged.

Both directions fail closed: blank `AUTH_SECRET` denies every session, blank
`APP_PASSWORD` refuses every login.

What it is not: the password is a **plaintext env var, not a hash** — there is
no user record to put one in. `/auth/login` has **no rate limiting**. Sessions
cannot be revoked one at a time; rotating `AUTH_SECRET` is the only "sign out
everywhere".

Local credentials are in `web/.env.local` (gitignored): `admin@gmail.com` /
`fb-agent2`. That password is a placeholder and is too weak for a public domain.

## Media is done

Storage moved to Supabase on 2026-08-09, after a `grilling` session that settled
eleven questions. The shape that was actually built is **not** the plan this file
carried before — `MEDIA_BACKEND=local|supabase` was rejected in favour of one
backend, and the publish-time upload was deleted rather than kept.

Nine steps, seven of them done. 260 tests passed at the time; the suite is
**302** now.

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

## The next task — the deploy

Both halves are authenticated now (`settings.api_key` on FastAPI, the session
cookie on Next), so this is the last thing left.

**API on Railway.** Root directory `api`, start command
`uvicorn app.main:app --host 0.0.0.0 --port $PORT`, **one replica**
(`generate.sweep_stranded` assumes a single writer), and the same `.env` values —
`DATABASE_URL` on the session pooler, `SUPABASE_BUCKET=fb-agent-media`. Run
`uv run alembic check` first; the suite builds its schema with `create_all` and
so can never catch a missing revision.

**Web on Vercel.** Root directory `web`, and **five** variables, none of them
`NEXT_PUBLIC_`:

| | |
|---|---|
| `APP_EMAIL`, `APP_PASSWORD` | the sign-in. Not the placeholder in `.env.local` |
| `AUTH_SECRET` | signs the cookie. `openssl rand -base64 32` |
| `API_KEY` | must equal the API's |
| `API_ORIGIN` | the Railway URL — **not** the `127.0.0.1:8000` default |

`API_ORIGIN` is the one that breaks quietly: left unset it points at the
serverless container itself, and every `/api/*` call fails against an API that
is plainly running. Set all five for Preview as well as Production, or a preview
comes up with a blank `AUTH_SECRET`, which denies every session and reads as a
broken login rather than a missing variable. Vercel bakes variables at build, so
a change needs a redeploy.

Unverified and worth checking first: `proxy.ts` is Next 16's renamed middleware
convention and has only ever run on the local dev server. If pages load straight
through without a sign-in, that file not being picked up is the first suspect —
it fails silently.

## Done on 2026-08-10 — the database moved

**Supabase Postgres, session pooler on `:5432`.** 2 pages / 954 source items /
6 drafts were migrated, ids and their gaps preserved, sequences resynced to
3 / 955 / 15. It has grown since — **10 / 2,435 / 17** on 2026-08-11.
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
- `npx eslint src` is **clean, zero problems**. The long-standing
  `set-state-in-effect` error at `review-list.tsx:87` is gone; both this file
  and `CLAUDE.md` described it as pre-existing and to be left alone, and neither
  noticed it being fixed. A warning there now is new — treat it as yours.
- Known unfixed: `sm:max-w-sm` in `web/src/components/ui/dialog.tsx` makes the
  image lightbox render 384px instead of its requested 1100px. One-word fix,
  never approved.
- **Every clock in the web app is the Page's, `Asia/Ho_Chi_Minh`.** The operator
  is in Melbourne and the client in Vietnam, and one clock is the decision — do
  not add a helper that renders an instant in the browser's zone, there is a
  note in `format.ts` where the last one was deleted. Two screens had it wrong
  (`getTimezoneOffset()` for "today" against planner stamps that are naive
  Ho Chi Minh); `pageToday()` / `pageNoon()` are the fix. The one thing that
  cannot be reached is `<input type="datetime-local">`, whose picker always
  offers the OS clock — which is why the publish field is seeded rather than
  empty, and why its label carries `(GMT+7)`.
- Row timestamps stay **UTC** (`models.py:26`) and are rendered into the Page's
  zone. That is storage, not a second clock.

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
