-- The two media buckets. Paste into Supabase's SQL editor and run.
--
-- Not a migration framework and not run by the app: this file exists so the
-- bucket settings are written down somewhere. Clicking them into the dashboard
-- works identically and leaves no record of *why* the bucket is public.
--
-- Storage sits on Postgres: `storage.buckets` is the bucket registry and
-- `storage.objects` indexes the files, but the bytes live in object storage and
-- are written over HTTP with the service key. Nothing here inserts a picture.
--
-- Re-runnable. `on conflict do update` so correcting a limit is the same
-- operation as creating the bucket.

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values
  -- Production. `SUPABASE_BUCKET` defaults to this name.
  ('fb-agent-media', 'fb-agent-media', true, 10485760,
   array['image/png', 'image/jpeg']),
  -- Development. A laptop and a Railway instance write to the same Supabase
  -- project with separate databases, so they hand out the same draft ids. Two
  -- buckets keep test drafts out of the bucket Facebook fetches from.
  ('fb-agent-media-dev', 'fb-agent-media-dev', true, 10485760,
   array['image/png', 'image/jpeg']),
  -- Shorts videos and CTA clips. `SUPABASE_YOUTUBE_BUCKET` defaults to this
  -- name. Video is a different kind of file with a different size ceiling,
  -- hence its own bucket (see `api/app/youtube/storage.py`).
  --
  -- 50MB, not the API's old 200MB: this Supabase project refuses a
  -- `file_size_limit` above 50MB (EntityTooLarge on create/update — measured
  -- 2026-09-04: 64MB rejected, 50MB accepted). The route's MAX_UPLOAD_BYTES
  -- matches, so an oversized clip is refused with a readable 400 rather than
  -- surfacing as a Supabase error behind the API.
  ('youtube-media', 'youtube-media', true, 52428800,
   array['video/mp4'])
on conflict (id) do update
set
  public = excluded.public,
  file_size_limit = excluded.file_size_limit,
  allowed_mime_types = excluded.allowed_mime_types;

-- `public = true` is load-bearing, and it is not a shortcut around signing.
-- Metricool stores the image *link* and Facebook fetches it when the post is
-- due, which may be days later. A signed URL expires before then: the old app
-- signed for 24h (`social-agent/src/lib/facebook/metricool-media.ts:17`) and 0
-- of its 105 published posts still have a working image.
--
-- Public here means "public to whoever holds the link", not browsable — buckets
-- do not list, and `media.filename` appends 6 random hex characters.

-- 10MB is a backstop, not the limit that should ever fire. `MAX_INSET_BYTES`
-- rejects an upload at 8MB with an error the operator can read
-- (`api/app/routes/drafts.py`); this one only catches a caller that bypassed it.

-- PNG and JPEG only, because that is all the app writes: heroes and insets are
-- PNG, composites are JPEG.

-- No RLS policies, deliberately. The old app's per-user folder policies
-- (`social-agent/supabase/migrations/20260603000000_facebook_media_storage.sql`)
-- exist because it had Supabase Auth and multiple users. This app has one
-- operator, writes server-side with the service key — which bypasses RLS — and
-- reads through the public URL, which a public bucket serves without a policy.
-- Copying them would add rules that never evaluate.
