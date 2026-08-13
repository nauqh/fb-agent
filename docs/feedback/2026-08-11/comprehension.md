# Our Comprehension — 2026-08-11 Feedback Analysis

Our technical analysis of each feedback item, verified by reading the code (not taking the report at face value).

---

## A. Regressions

### A1 — Padding/text size not working
**Root cause confirmed:** The Review screen (`composed-image.tsx`) hardcoded padding (`6% 4%`) and font size (`clamp(10px, 4.1cqw, 19px)`), ignoring per-Page layout overrides that were already correctly stored in `page_layout`. The write path was never broken — `PATCH /layout` stored values correctly, and the Global preview read them. Only the Review preview was wrong.

**Three failure modes identified:**
1. Review preview ignored overrides — **the actual bug**
2. Existing drafts not redrawn on layout change — **closed by decision** (stale window theoretical; drafts published/rejected before layout changes reach them)
3. Page switcher could query wrong Page's layout — **fixed** by keying layout query on draft's `page_id`

**Incidental fixes:** Watermark drew red "no asset" box for Pages without committed files (8 of 10); watermark position used wrong ratio (`edge_margin_ratio` vs `watermark.top_ratio`).

---

## B. Missing screens/controls

### B1 — Overview page
**Prior art:** Old app had `overview-panel.tsx`, `viral-posts-panel.tsx`, `use-saved-viral-posts.ts`, `lib/facebook/overview-performance.ts`.

**Data source decision:** Metricool `/stats/facebook/posts` takes our `blogId` — a read, not Graph API integration. Probed live: 657 posts/90 days, best 160K reactions.

**Key findings from probe:**
- `sortcolumn` accepted but ignored → we sort client-side
- `engagement` null on all rows → compute as reactions+comments+shares
- 30-day window not "dead Page" — belief came from sort bug; measured: 1/28 zero-reaction over 7d, 1/219 over 30d, 4/657 over 90d

**Two halves:**
- Performance — read-only from Metricool analytics
- Saved posts — new `saved_post` table (reference outlives analytics window)

**Reuse** = "Write again" on saved post → runs as topic (not Source Item, which would summarise our own caption).

---

### B2 — Manual page
**Client's screenshot showed topic field**, but old app's Manual was `GenerateMode = "ai" | "manual"` where manual = form with hook, caption, first comment, optional image — **no model call**.

**First attempt (bd84736)** built topic-only page — wrong feature.

**Corrected (1de814b):** `/manual` with two tabs:
- **Write it yourself** — `POST /drafts/manual`, no model, optional upload → hero
- **From a topic** — the topic strip from Sources dock (does call writer)

**Design choices:**
- Upload becomes hero, card drawn around it (not published raw)
- Image optional → warning, not refusal
- Brand rules recorded as warnings, not enforced
- Live card preview beside fields (old app lacked this)
- Kept thin — client has future plans for this page

---

### B3 — Per-field regeneration
**Old app had:** `regenerate-field-control.tsx`, `draft-regenerate.ts`, `RegeneratableField` union.

**New app lost it** — writer produces all fields in one call; only hero regeneration existed.

**Solution:** `POST /drafts/{id}/regenerate?field=hook|caption|first_comment`
- Kept fields passed as context to writer (new caption must match kept hook)
- Hook regeneration triggers recomposite (hook is in `DRAWN_FIELDS`)
- Synchronous (one call, operator waits)

---

### B4 — Circular inset (full old app flow)
**Old app stored per-draft:** border width, border colour, diameter, centre, generation prompt in `ai_metadata.portraitInset`.

**First pass design** put controls only on Page — narrower than old app.

**Revised design (matching codebase pattern for `inset_size_px`):** Layout = default, Draft overrides, null = inherit.

**Three pieces:**
1. **Per-Page (Global)** — Portrait group: diameter, border width (0=none), border colour. Columns exist on `page_layout`; UI only.
2. **Per-draft (Review drawer)** — New nullable columns `Draft.inset_border_width_px`, `Draft.inset_border_color` (null = Page's). Compositor prefers draft values.
3. **AI-generated inset** — Upload/Generate tabs, `Draft.inset_prompt`, `POST /drafts/{id}/inset-generate`. **Still open.**

**Defects found/fixed while building (tests wouldn't catch — wrong ring still = valid PNG):**
- Zero-width border filled disc (Pillow `width=0` = fill shape) → fixed
- Thick ring clipped — canvas padding constant 3px only covered 2px border; at 48px max, overhang 24px → `PortraitLayout.ring_pad` now derives padding from border width

---

## C. Generation options

### C1 — Template choice per draft
**Current:** Per-Page only (`page_layout.template`).

**Needed:** `Draft.template: str | None` (null = Page's), threaded through `layout_for.resolve`. Toggle at Generate + Review; switch recomposites free (hero reused).

**Note:** Review preview couldn't draw `full_overlay` at all — same root as A1.

---

### C2 — Generate without image
**Current:** `build_image` always produces hero (or warning). Publish refuses draft with no composite. Metricool payload always sends `media: [url]`.

**Solution:** `no_image` flag on generate request → stored on Draft → skips `build_image` → publish sends body with no `media`. Test against Metricool first (FB may refuse no-media post).

---

### C3 — Use RSS feed image
**Current:** `SourceItem.image_url` already carried from feed, displayed on source cards.

**Solution:** `hero_from_source` toggle + column → `hero.from_url` fetches/decodes/stores as hero (no Gemini). **Narrowed to RSS only** — competitor/tweet images would be reposting rival creative under our watermark. Enforced server-side.

**Rights note:** Fetched image written to our bucket (feed images can vanish; FB fetches at publish time — same trap as Metricool docs warn).

---

### P1 — AI-sourced photos from web (parked)
**Not in scope.** Gemini cannot browse — needs external search API + rights judgement. Two shapes if ever picked up:
- Licensed stock (Unsplash/Pexels) — clear licence, but narrow for historical people/events
- General web search — unknown owners, silent rights decision per post

**Overlap check first:** C3 (RSS image) + B4 (AI-generated inset) may already satisfy "real photo not AI-looking" intent.

---

## D. Publishing & scheduling

### D1 — Approve button
**Current:** `Approve` sets `status=approved`, removes from queue, reversible via `unapprove`. Publish does not require it.

**Analysis:** Client correct — Approve is queue movement with no consequence. Recommend: stop writing `APPROVED` status; let three scheduling actions (D2) take draft out of queue. Keep enum value for existing rows.

---

### D2 — Publish Now / Schedule / Next Available Slot
**Current:** One Publish button + datetime field (empty = ASAP, floor now+2min).

**Solution:** Three buttons. "Next Available" walks Page's configured slots, checks Metricool planner for collisions (uses existing `list_scheduled`). No local schedule state (ADR-0001 holds).

---

### D3 — Time slots in Page Settings
**New table:** `page_time_slot(page_id, minute_of_day)` — **same times daily** (no weekday dim; operator chose flat list). Not ADR-0001 violation — slots are *policy*, not schedule state. Times in `Asia/Ho_Chi_Minh`.

---

### D4 — First comment delay
**Blocked:** Metricool scheduler has **no delay field**. Old app had it via Postiz (`delay` param, default 5s).

**Options:**
1. Graph API publish after Metricool posts — needs page token, publish detection, delayed job (no worker, single replica)
2. Move to Postiz — reverts prior decision
3. "Not available through Metricool"

**Recommendation:** Spike Metricool API live (docs wrong twice already), then (3) unless free.

---

## E. Removals

### E1 — Drop hashtags
**Operator declined 2026-08-11** (hashtags in use, would raise with client).
**Client restated 2026-08-12** → operator reversed.

**Shape:** Column stays (20/21 drafts have values, 1 in Metricool planner with tags in published text — dropped column has no undo). Nothing writes to it. Writer/API/UI no longer produce/send. Pre-existing drafts **do not publish** stored tags (half-removal = not removing). Pinned by test `test_the_caption_is_the_post_the_hook_and_old_hashtags_are_not`.

**Eight sites changed:**
1. `routes/drafts.py:_post_text` — stopped appending (only site changing what FB sees)
2. `writer/agent.py` — field + validator gone from `DraftContent`
3. `writer/validators.py` — `normalise_hashtags` deleted
4. `routes/drafts.py:DraftEdit` — field + normalise branch gone
5. `generate.py` — no longer copies writer's tags to Draft
6. `draft-detail.tsx` — Hashtags input, Form field, toForm
7. `facebook-preview.tsx` — blue tag line under caption
8. Types, API, fixtures — types, DraftEdit union, 6 fixtures

**`schedule-list.tsx` still parses tags from planner text** — reads old system's 302 posts, unrelated to column.

---

## F. Needs decision/spike

### F2 — Full automation for time-sensitive content
**Client marked optional.** Needs: scheduled trigger (no cron/worker), classifier in writer, policy for no-human-in-loop (bigger than feature; `_editable` freezes published drafts because no undo). Parked — revisit after D2/D3.

---

### F3 — Vercel/VPS/YouTube tool
**Infrastructure, touches old repo.** Current deploy: Vercel (web) + Railway (API) — API is long-running FastAPI with background runs, single-writer (`generate.sweep_stranded`); serverless wrong shape. "Continue using Vercel as server" is half-true — API stays on Railway.

YouTube tool unsurveyed — needs own scoping pass.

---

## Decisions Taken (2026-08-11)

1. **A1 stale composites:** No redraw button, no recomposite on save. Draft keeps baked PNG. Reasoning: by time layout change lands, draft already published/rejected.
2. **B2 Manual page:** Move (not duplicate). Topic field leaves Sources dock; dock keeps only Cart.
3. **D3 time slots:** Same times daily. Flat list (08:00, 13:00, 19:00). Next available walks forward through days at those times.

---

## Questions for Client

1. **D4** — If Metricool has no delay field, is Graph API path worth cost, or is "not available" acceptable?
2. **F3** — Scope of YouTube tool; confirm API stays on Railway.
3. **P1** — Does C3 + B4 already cover "AI image sourcing" intent?
4. **E1** — Hashtags: operator raising directly; no action needed here.