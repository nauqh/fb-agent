# Our Address — 2026-08-11 Feedback Resolution

What was shipped to `main` (merged from `client-feedback` branch), verified in browser, with tests passing.

---

## Status Summary

| Item | Status | Shipped | Notes |
|------|--------|---------|-------|
| **A1** | ✅ Done | 2026-08-11 | Review preview fixed |
| **B1** | ✅ Done | 2026-08-12 | Overview page |
| **B2** | ✅ Done | 2026-08-11 | Manual page (corrected in 1de814b) |
| **B3** | ✅ Done | 2026-08-11 | Per-field regenerate endpoint |
| **B4 (settings + per-draft)** | ✅ Done | 2026-08-11 | Border width/colour, diameter |
| **B4 (AI-generated inset)** | ⏳ Open | — | Only feature item remaining |
| **C1** | ✅ Done | 2026-08-11 | Template toggle at Generate + Review |
| **C2** | ✅ Done | 2026-08-11 | `no_image` flag |
| **C3** | ✅ Done | 2026-08-11 | `hero_from_source` (RSS only) |
| **D1** | ✅ Done | 2026-08-11 | Approve = queue movement only; stop writing APPROVED |
| **D2** | ✅ Done | 2026-08-11 | Three publish buttons + Next Available Slot |
| **D3** | ✅ Done | 2026-08-11 | `page_time_slot` table, flat daily list |
| **D4** | ❓ Blocked | — | Needs Metricool spike |
| **E1** | ✅ Done | 2026-08-12 | Hashtags removed from writer/API/UI; column retained |
| **F2** | ⏸ Parked | — | Revisit after D2/D3 |
| **F3** | ⏸ Parked | — | Infra; YouTube tool needs scoping |
| **P1** | ⏸ Parked | — | C3 + B4 may cover intent |

---

## Migrations Applied to Production (5)

| Revision | Purpose |
|----------|---------|
| `3749e016826e` | Inset ring: `Draft.inset_border_width_px`, `inset_border_color` |
| `20974f89ec28` | `hero_from_source` column |
| `e95cf1ff6545` | `page_time_slot` table |
| `9a8d2213232a` | `Draft.template`, `Draft.no_image` |
| `85d4da17f9d6` | `saved_post` table |

All nullable, backfilled, or new tables — no existing row rendering changed. Two needed hand-fix after autogenerate wrote non-nullable boolean with no default (fails at deploy, not locally).

---

## Code Changes by Item

### A1 — Review preview padding/text size
- **Web:** `ComposedImage` now takes resolved layout + Page; draws `full_overlay` + `card`. Deleted `LAYOUT` fixture (`lib/fixtures/pages.ts`) and dead `lib/api/config.ts`.
- **API:** No code change — write path was correct. Layout query keyed on draft's `page_id` (not switcher).
- **Incidental:** Watermark now follows `page.watermark()`; position uses `watermark.top_ratio`.

### B1 — Overview page
- **API:** New `GET /overview/performance` (Metricool analytics read), `GET/POST/DELETE /overview/saved-posts` (CRUD on `saved_post`).
- **Web:** `/overview` page with Performance + Saved tabs. "Write again" on saved post → generate with topic.

### B2 — Manual page
- **API:** `POST /drafts/manual` — creates `Draft` with `status=REVIEW`, optional upload → hero, `build_image` reuse, warnings recorded not enforced.
- **Web:** `/manual` route with tabs: **Write it yourself** + **From a topic**. Live card preview on hand-written tab. Sources dock simplified (no `usingTopic`).

### B3 — Per-field regeneration
- **API:** `POST /drafts/{id}/regenerate?field=hook|caption|first_comment` → `writer.rewrite(page, source, topic, field, keeping)` → updates field + `highlight_phrases` if hook → recomposites if hook changed.
- **Web:** Regenerate buttons in review drawer per field.

### B4 — Circular inset (settings + per-draft)
- **API:** Columns `Draft.inset_border_width_px`, `Draft.inset_border_color` (nullable, null = Page's). `page_layout` already had `portrait_border_width_px`, `portrait_border_color`. Compositor `Inset` prefers draft values.
- **Web:** Global → Composed Image: Portrait group with hatched stand-in disc. Review drawer: Ring control with "Use Page's" reset.
- **Fixes pinned by tests:** Zero-width border no longer fills disc; thick ring padding derived from border width (`PortraitLayout.ring_pad`).

### C1 — Template choice per draft
- **API:** `Draft.template: str | None` (null = Page's). `layout_for.resolve_draft` threads it. Generate request accepts `template`. Review PATCH accepts `template` → recomposites free.
- **Web:** Toggle at Generate (defaults to Page's). Toggle in review drawer.

### C2 — Generate without image
- **API:** `GenerateRequest.no_image` → `Draft.no_image` → `build_image` skipped → publish sends body with no `media`.
- **Web:** "No image" checkbox beside Generate button.

### C3 — Use RSS feed image
- **API:** `GenerateRequest.hero_from_source` → `Draft.hero_from_source` → `hero.from_url` fetches/decodes/stores as hero (no Gemini). Enforced RSS-only server-side.
- **Web:** "Use source picture" toggle beside Generate (enabled only for RSS sources).

### D1 — Approve button
- **API:** `approve_draft` sets `status=APPROVED` (queue movement). `unapprove_draft` returns to `REVIEW`. `publish_draft` does not require `APPROVED`. **Decision:** stop writing `APPROVED`; keep enum for existing rows.
- **Web:** Approve/Unapprove buttons remain; Publish actions (D2) are primary queue exit.

### D2 — Three publish actions
- **API:** `POST /drafts/{id}/publish` accepts optional `when`. `POST /drafts/{id}/schedule-next` walks `page_time_slot`, checks Metricool planner via `list_scheduled`, returns chosen slot.
- **Web:** Three buttons in review drawer: **Publish Now**, **Schedule…**, **Next Available Slot**.

### D3 — Time slots in Page Settings
- **API:** `page_time_slot` table (`page_id`, `minute_of_day`). CRUD endpoints. `next_slot` walks slots + checks planner.
- **Web:** Page Settings → Time Slots: add/remove/edit times (HH:MM, `Asia/Ho_Chi_Minh`). Flat list, no weekdays.

### E1 — Drop hashtags
- **API:** `writer/agent.py` — field + validator removed from `DraftContent`. `writer/validators.py` — `normalise_hashtags` deleted. `routes/drafts.py:_post_text` — stopped appending (only site changing FB payload). `DraftEdit` — field + normalise branch removed. `generate.py` — no longer copies writer's tags.
- **Web:** `draft-detail.tsx` — Hashtags input, Form field, `toForm` removed. `facebook-preview.tsx` — blue tag line removed. Types, API client, fixtures updated (6 fixtures).
- **Retained:** `Draft.hashtags` column (20/21 drafts have values, 1 in planner with tags in published text). `schedule-list.tsx` still parses tags from planner text (old system's 302 posts).

---

## Quality Gates

| Check | Result |
|-------|--------|
| API tests (`pytest -q`) | 353 passed (was 304; 360 before E1 removed 7 hashtag tests) |
| Alembic check | Clean |
| Web TypeScript (`tsc --noEmit`) | Clean |
| Web ESLint (`eslint src`) | Clean (0 warnings) |
| Browser verification | Every item driven at `localhost:3000` |

---

## Open Work

### B4 — AI-generated inset (only feature item left)
- **Needed:** `Draft.inset_prompt` column, `POST /drafts/{id}/inset-generate`, Upload/Generate tabs in review drawer.
- **Notes:** `models.py:552` and `layout.yml` portrait block comments currently state "nothing generates the inset" — must be rewritten.

### D4 — First comment delay
- **Blocked on:** Metricool API spike (live, not docs — docs wrong twice already).
- **If no delay field:** Recommend "not available" (option 3) unless Graph API path is free.

### F2 — Full automation
- **Parked.** Revisit after scheduling (D2/D3) lands.

### F3 — Vercel/VPS/YouTube
- **Parked.** Separate infra work. API stays on Railway (long-running FastAPI). YouTube tool needs scoping.

### P1 — AI-sourced web photos
- **Parked.** Check if C3 (RSS image) + B4 (AI-generated inset) satisfy intent first.

---

## Deploy Note

**Railway must set `METRICOOL_PUBLISH_AS_DRAFT=false`** for real Facebook posts. See `metricool-publishing-review-2026-08-12.md` for the rest of the risks (duplicate-on-retry, timezone bug in `get_schedule`).

**Done — the operator set it on Railway, and the planner proves it took.** Read
live 2026-08-16: the five drafts pushed on 08-14 (48, 53, 54, 55, 57) are
`draft=false status=PUBLISHED`, out on Facebook on 08-15. The local `.env` stays
`true` and should — that is the rehearsal environment, and nothing on a laptop
should be able to publish to an audience.

Do not read this file for the flag's current value again. It said `true` for
four days after it stopped being true, and was quoted back as fact. The value
lives on Railway; the *evidence* is the planner, which `list_scheduled` will
answer for at any time.