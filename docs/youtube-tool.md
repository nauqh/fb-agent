# The YouTube tool

Rebuild of the old YouTube automation tool (`D:\Laboratory\social-agent`, read
only) in this repo. Same workflow — download → trim → CTA-concat → store, then
a Metricool planner post per channel, then reconciliation — in Python, with
what each step cost someone real time written beside it.

## What is built

| | |
|---|---|
| **Produce** (`/shorts`) | paste a link → enqueue → worker downloads, trims to N seconds, appends the CTA clip, stores the mp4 |
| **History** (`/shorts/history`) | every job, newest first; completed rows play and download |
| **Overview** (`/shorts/overview`) | a channel's videos ranked by views, from Metricool's `stats/youtube/videos`, with a previous-window comparison and short/video kind joined from the planner |
| **Not built** | steps 4–6 of the old tool: Metricool scheduling, reconciliation, schedule actions. The `youtube_schedule` table exists empty in the live database — a known orphan from an earlier draft of the migration, not a missing revision |

The old tool was two applications glued by a queue: Vercel enqueued, a VPS
worker (`yt-dlp` + ffmpeg + Cobalt under pm2) processed, BullMQ/Upstash carried
the jobs. That whole topology is gone. The stack decisions, with the reasons:

| Piece | Old | New | Why |
|---|---|---|---|
| Download | yt-dlp CLI exec + shell escapes | `yt_dlp` library | options dict replaces every flag; no escaping surface |
| Cobalt | Docker, primary downloader | **dropped** | no public API (self-host only); production logs show it always fell through to yt-dlp with `error.api.youtube.login` |
| Queue | BullMQ + Upstash Redis + VPS worker | `youtube_job` table + in-process asyncio worker | the repo already runs this shape for drafts/generate; five videos a day does not need a broker. One writer process — no `FOR UPDATE SKIP LOCKED`, deliberately: the startup sweep would kill a second worker's live runs |
| Storage | Supabase Storage | same, own bucket | `youtube-media`, public, mp4-only, 50MB cap (the project refuses a bucket limit above 50MB — measured) |
| Scheduling | bespoke client | `app/publish/metricool.py` (when built) | same `v2/scheduler/posts`, live-verified, already publishes for real |

## The old tool, in one paragraph

Era 1 (2026-05) uploaded with the YouTube Data API and OAuth — dead code now.
Era 2 (2026-07) published through Metricool's planner: `autoPublish` posts
created by the app, plus status reconciliation against what Metricool actually
did. The Connect-a-channel OAuth UI was vestigial. What survived into this
rebuild: the ingest → download → trim → concat → store pipeline, the planner
scheduling shape, the reconcile heuristics, the naive-plus-zone datetime rule,
the 100-char title cap, the "publish now = planner post at now+2min" trick.

## What the app does now

**Ingest.** `/shorts/{id}`, `watch?v=`, `youtu.be/`, or `@handle/shorts`. A
channel URL means "top-N Shorts by view count" (or a hand-picked subset): the
picker listing comes from the official API when `YOUTUBE_API_KEY` is set
(titles, thumbnails, ≤180s filter), else yt-dlp flat-playlist ranked by
`view_count`. Enqueue writes one `youtube_job` row per video and returns ids
immediately — the worker fills them.

**Process.** yt-dlp library with the old tool's discipline: cookiefile from a
*work copy* (the master browser export is never handed over), player-client
rotation on bot-check signatures (`tv_embedded,mweb` → `android,web` →
`ios,mweb`), `--no-cookies` retry on cookie-error signatures, sleep intervals
2–8s, optional residential proxy for datacenter egress. ffmpeg subprocess:
trim to `trim_duration` (default 3s, clamp 1–60), concat the CTA scaled+pad to
source dims at fps=30, libx264/aac, `+faststart`. Progress 20/35/50/90/100 on
the row; the screen polls. Startup sweep marks stranded `PROCESSING` rows
`FAILED` — safe because exactly one worker exists.

**Store.** `<yyyy-mm>/{job_id}_processed.mp4` in the `youtube-media` bucket.
Public is load-bearing: Metricool stores the *URL* and YouTube fetches the
file when the post is due, possibly days later — the old app's signed URLs
expiring at `publishAt+2h` is why 0 of its 105 published posts still have
working images.

**CTA clips.** Library rows; the worker fetches the clip at job time from the
row's public URL. Upload is browser-direct (below) — same public-URL rule
applies to the clip's own URL.

**CTA upload — browser-direct, never through this app.** The API mints a
path and a signed upload URL; the browser `PUT`s the mp4 straight to Supabase
with the token as its Bearer; the API then creates the row over a path it
minted *and* can prove received bytes (regex guard + HEAD). Three facts from
production, each found the expensive way:

- The old multipart route **413'd in production** at Vercel's serverless
  request-body ceiling (~4.5MB, not raiseable) — and locally at Next's 1MB
  middleware buffer cap (fixed by `proxyClientMaxBodySize`, but that only
  unmasked the Vercel one). Bytes no longer cross the app at all.
- The wire shape is not in the docs: mint = `POST
  /object/upload/sign/{bucket}/{path}` with the service key; consume = **PUT
  the same path** with `?token=`, token as Bearer, `x-upsert` header. A POST
  on the consume path *re-signs* instead of storing.
- The upload token has no role claim, so the storage server's bucket lookup
  runs as anon — and `storage.buckets`/`storage.objects` RLS had zero
  policies, so the token was denied everything. Two policies scoped to
  `youtube-media` fix it (objects INSERT, buckets SELECT, both for anon;
  see `supabase/buckets.sql`). The service key bypasses RLS; a token does not.

**Overview.** `stats/youtube/videos` returns the channel's *whole catalog* —
the start/end window is accepted and ignored, so the date split happens in the
route on `publishedAt` (epoch milliseconds). Views are the rank, not
engagement: these channels draw near-zero likes/comments while views span
orders of magnitude. `days=0` (All) is the default because a catalog is
bounded, and has no `previous` to compare against. The planner read is joined
only for short/video kind. A video with no `publishedAt` lands in no window.

## When steps 4–6 get built (the Metricool half)

Verified against Bible Focus's live planner rows — the real post shape is:

```json
{
  "autoPublish": true, "draft": false,
  "providers": [{"network": "youtube"}],
  "youtubeData": {"title": "…", "type": "short|video", "privacy": "public",
                  "category": "EDUCATION", "madeForKids": false},
  "publicationDate": {"dateTime": "2026-06-06T22:02:00", "timezone": "Asia/Ho_Chi_Minh"},
  "media": ["<public mp4 url>"]
}
```

Notable: `category` exists and the old study missed it; the title lives inside
`youtubeData.title` (no root `ytTitle` on live rows); row-level `status` is
null — the provider-level `status: PUBLISHED` + `publicUrl` is where the truth
lives, which is what reconciliation must read. Reconcile heuristics (post-gone
+ past-due ⇒ COMPLETED; 5/30-minute windows; provider failure ⇒ FAILED) are
observed behavior, not spec — port them with their comments from the old repo
(`youtubeMetricoolSyncService`), or re-derive from production before deleting
them. Schedule actions: pause/resume/retry/publish_now/delete; **reschedule =
delete + re-create, never PUT** — Metricool has no in-place update and a PUT
duplicates the post.

## Traps (each cost real time; some twice)

- **Metricool does not re-host media.** Normalize echoes the URL back. The
  bucket URL must resolve at publish time — forever, not just when scheduled.
- GETs to Metricool must **omit `Accept: application/json`** (500 otherwise).
- `publicationDate.dateTime` is naive local + separate `timezone`; an offset
  suffix is rejected.
- **Metricool has no in-place update.** PUT duplicates; delete + re-create.
- **yt-dlp bot-checks beat everything except rotation.** Player-client
  variants, work-copy cookies, sleep intervals, proxy. Removing any of these =
  quiet download failures on a server.
- **Cobalt always fell back to yt-dlp** on datacenter IPs — that *was* the
  fallback trigger. Dropping it removed a thing to diagnose.
- **Pinned Gemini / API model ids rot silently**; `models.list()` reports
  models that 404 on use. Verify with a real call.
- **A green suite is not a working screen** (CLAUDE.md has the full text) —
  the CTA upload worked in every test and still failed twice in production,
  on two different ceilings, before it worked once end to end.

## Data model & API

`youtube_job` — the queue row *is* the record: url, source_type
(`direct`/`channel_short`/`upload`), short id + resolved url, rank and
view/like snapshots, `trim_duration`, `cta_template_id`, status
(`QUEUED`/`PROCESSING`/`COMPLETED`/`FAILED`), progress, `processed_video_path`,
error. `cta_template` — title + `cta_video_url` (public). `youtube_schedule`
— orphan, empty, waiting for step 4.

Routes live under `/youtube`: jobs CRUD + `/{id}/download`, `channel-shorts`
picker, `config` (presence-only readout), `cta-templates` (`upload-url` +
`complete`, list, delete), `brands` (Metricool profiles with a channel), and
`overview?brand_id&days`.

Env: `YOUTUBE_API_KEY` (optional, switches shorts listing to the official
API), `YTDLP_COOKIES_FILE`/`_WORK_FILE`, `YTDLP_PROXY_URL` (datacenter
egress), `SUPABASE_YOUTUBE_BUCKET` (default `youtube-media`), the Metricool
token trio, and the existing Supabase pair. `scripts/shorts_dev_server.py`
runs the whole tool against a throwaway sqlite file and a directory store,
because `app/db.py` refuses anything but Postgres and the production database
is off limits.
