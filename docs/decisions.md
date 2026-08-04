# Rebuild decisions

Design session, 2026-08-02. Rebuild of the Facebook Agent from the Next.js /
Supabase monolith at `D:\Laboratory\social-agent` (~35k LOC) into Python +
FastAPI + SQLite with a fresh Next.js frontend.

**Driver:** the existing stack is too complex to maintain. Feature parity is
explicitly *not* a goal; pruning is encouraged.

This file records *what was decided and why*. How the app is assembled is
[design.md](design.md); the tables are [data-model.md](data-model.md).

Three decisions were significant enough to get their own ADR:
[0001](adr/0001-no-local-schedule-state.md) ·
[0002](adr/0002-single-operator-no-tenancy.md) ·
[0003](adr/0003-page-is-the-only-identity.md)

## v1 is one page, History Retraced

Decided 2026-08-03, after Phase 1's backend landed. The other nine pages are
dropped — not deactivated, not seeded — and come back as inserts when they are
wanted. `is_active` goes with them: one page means the flag is never false.

This also ends the Supabase dependency. With prompts extracted to files and the
layout to `layout.yml`, the entire migration is four constants
(`name`, `facebook_page_id`, `metricool_blog_id`, `daily_quota`), so
`scripts/seed_pages.py` — which read production Supabase and Metricool at
runtime — collapses to `scripts/seed_page.py`, and `SUPABASE_URL` /
`SUPABASE_SERVICE_ROLE_KEY` leave `.env`.

## The prompts are files

`system_prompt`, `overlay_prompt` and `image_prompt` move out of `page` and into
`api/prompts/*.txt`, read on every call so an edit needs no restart.

The prompts are the product, and they are the most-edited thing in the system.
In a database column they were invisible to git, unreviewable, and un-revertable
— and they had already rotted: the stored copies still described a 75% hero and
a circular logo long after the code moved to a growing panel and a natural-aspect
logo. History Retraced's overlay prompt carried that stale block a second time.

The two numbers shared with the compositor are tokens, `{panel_pct}` and
`{highlight_color}`, substituted from `layout.yml`. Substitution is `str.replace`
rather than `str.format`, so a stray brace in a prompt cannot raise mid-generation.

## v1 is a draft factory

Four screens: **Sources** · **Generate** · **Review** · **Settings**.

Sources → Cart → Generate → review the Draft and its Composed Image. It stops
there. Pushing to Metricool and the calendar are v2, deferred together with the
move off local file storage (see [Deferred](#deferred-to-v2)).

## Stack

| Piece | Choice |
|---|---|
| Repo | `fb-agent`, new, `api/` + `web/` |
| Backend | `uv` + `fastapi[standard]` |
| Database | SQLite via SQLModel, stock settings, `create_all` (Alembic at the Supabase move) |
| Writer agent | Pydantic AI, `GoogleModel` |
| Image generation | `google-genai` direct (image output, not a typed agent) |
| Image compositing | `resvg-py` + `fontTools` + Pillow |
| Frontend | Fresh Next.js, full rewrite |
| Background work | `BackgroundTasks` + placeholder Draft rows + client polling |

Models carried over: text `gemini-3.5-flash`, hero image `gemini-2.5-flash-image`.
The old system stored `model_id` per Page and then set all ten rows to the same
value, so it becomes env (`GEMINI_TEXT_MODEL`, `GEMINI_IMAGE_MODEL`) — note
these did already override the *code* defaults, so the code default is the value
that must not be trusted.

## Cut, with the evidence

Each of these was verified against the running code or production data, not
assumed.

**Cron, BullMQ, Redis, the worker process, the Hetzner VPS.** The Facebook
generate queue is gated behind `FACEBOOK_GENERATE_ASYNC=1`, commented out in
both `.env.local:80` and `.env.local.example:72` — the default path was already
Next's `after()`. `processPendingFirstComments()` is a stub returning `[]`
(`facebookPublishService.ts:638`). Metricool receives `autoPublish: true` and
`firstCommentText` (`metricoolService.ts:306,540`), so it owns publishing and
the first comment. Status sync was already pull-on-read, not scheduled
(`facebookPublishService.ts:757`).

**Facebook Graph OAuth, `facebook_connections`, `facebookGraphService.ts`.** The
page list comes from Metricool (`facebookPagesService.ts:4`). Graph survived
only in `api/facebook/connection` and the OAuth callback.

**Postiz**, entirely — Metricool is the sole publish provider.

**`facebook_schedules`** — see ADR-0001.

**Overview + Library + `facebook_saved_viral_posts`.** The "recycle our own
winners" feature — a fourth source outside the three in scope. Removing it also
deletes the `savedViralPostIds` branch threaded through the whole generate
pipeline.

**`brand_key` and the brand/page duality** — see ADR-0003.

**The `full_overlay` layout.** Every overlay setting existed twice, once per
layout — ~26 columns. Production over 464 drafts: `card` 411, `full_overlay` 53.
Over the last 14 days: **64 `card`, 1 `full_overlay`.** The layout was
effectively abandoned. Keeping one form deletes the doubled columns,
`template-layout-prompts.ts`, `resolveImageGenSystemPromptForLayout`, and the
layout picker.

**Supabase auth, RLS, `user_id`** — see ADR-0002.

**LangGraph.** Six nodes, linear, zero conditional edges
(`facebookGenerateGraph.ts:743`); `summarizeNode` no longer calls a model at all,
it maps each post to itself (`:352`). The real pipeline is one structured Gemini
call per Source Item. One `async def` covers it.

## Kept, and why

**The operator workflow.** Sources → Cart → Generate → Review is not the
problem; the code structure was.

**The compositor**, as a hero image plus text panel, highlight phrases and
watermark — no headline badge, which went with the `full_overlay` layout that
was its only caller. Ported to `resvg-py` + `fontTools` + Pillow — the old code
already rasterised via resvg rather than sharp (`composite-font.ts:24`) and
measured via `opentype.js` advance widths (`overlay-text-measure.server.ts:19`),
both of which have exact Python equivalents reading the same `Arial-Bold.ttf`.
**Pixel parity is not required** — the layout engine is re-curated to one good
form rather than ported line by line.

**Placeholder rows + polling** for generation progress, matching current
behaviour.

**The prompts.** These are the product. System ~1.7–2.4k chars, image-gen
~2.3–2.7k, overlay ~1.5k, per Page.

## Enforced, not merely checked

`validation.ts` encodes real brand rules — hook ≤65 words, no question mark in
the hook, ≤5 recap lines each starting with an emoji, first comment 2–3
paragraphs, body 1500–2100 chars, birth/death years present, no meta-phrases —
and today they produce warnings nobody acts on. In the rebuild each becomes a
Pydantic AI `@agent.output_validator` raising `ModelRetry` with the specific
failure, capped at two retries. Same call count in the happy path.

## The model is three tables

`page`, `source_item`, `draft`. Down from eight tables plus a 54-column
templates table. A `competitor` table, a `page_competitor` join, a `feed` table, a
`generation_event` table and a cart table were each designed and then rejected —
[data-model.md](data-model.md#what-was-considered-and-rejected) records why, and
the production evidence that settled each one.

## One layout, one image size, in a config module

There is no per-page styling. Every layout constant — image size, font size,
panel geometry, colours, badge, paddings — moves to
[`api/config/layout.yml`](../api/config/layout.yml), taking **History Retraced's
values as the standard**. `PAGE` falls from 29 columns to 12. Model ids stay in
env, not the file: they are deployment config and get retired upstream.

Ten of those columns had already collapsed on their own: across all ten page
rows the four paddings, `panel_color`, `text_align` and `model_id` each held
exactly one distinct value, `brand_watermark_text` was byte-identical to
`page_name` in 10/10, and font min/size/max were equal in 10/10 — there is no
autofit, `planOverlayLayout` reads the size once and grows the panel instead.

The headline badge is gone rather than standardised: it renders only under
`if (isFullOverlay && label)`, so cutting the `full_overlay` layout cut the
badge. Hot Tub Timeout's `BEST TUB EVER` goes with it. Rounded corners were
already dead in production — the compositor hardcodes a zero radius.

Values were checked against the composite path a `card` draft actually takes,
not only against the template row. Two per-draft overrides exist in
`ai_metadata` (`overlayTextColor`, `overlayHighlightColor`); across 400 drafts
**399 leave both null**, so the code fallbacks `#ffffff` and `#F5C542` are what
production renders, and they become the config values.

Only `daily_quota` and `watermark_image_path` stay per-page — policy and a
per-page asset. The prompts were the third until they became files. Details and
the full before/after table are in
[data-model.md](data-model.md#layout-is-config-not-data).

## Migration

There is effectively nothing to migrate. `scripts/seed_page.py` inserts four
constants for History Retraced; the prompts were lifted into `api/prompts/` once,
by hand, and are now source files. The other 49 template columns are dropped.
Competitors re-sync from Metricool. Source Items are transient by nature. The 464
drafts stay behind — 237 are already published and Metricool holds that record.

**The watermark becomes a committed file.** In the current Supabase project every
watermark path 404s; the bucket was cleared to 8 recent draft jpgs. The old
compositor reads the logo back by storage key and treats a failed download as
"no logo", so output silently degraded to the page name in text — no error, no
log, posts kept shipping. The genuine assets were recovered from the *previous*
Supabase project, which still holds 1491 objects.

They now live in `api/assets/watermarks/`, beside `Arial-Bold.ttf`, because they
are the same kind of thing: a fixed input the renderer cannot work without.
Versioned with the code that reads them, so they cannot evaporate again, and a
clone is complete. A missing file should be an error, never a quiet fallback.

## Deferred to v2

- Approve → Metricool push. Metricool's servers fetch the image URL themselves
  (`metricoolService.ts:182`), so this needs a publicly reachable HTTPS host and
  cannot work against local disk.
- The calendar, which reads live from Metricool and has nothing to show until
  the push exists.
- `MediaStore` swap from `LocalMediaStore` to Supabase Storage or R2. The
  interface (`save(bytes) -> public_url`) exists from day one so this is one
  class, not a refactor.

**Accepted risk:** the riskiest integration ships unproven, and Composed Images
are only ever seen locally in v1.
