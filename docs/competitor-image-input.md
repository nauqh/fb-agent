# Competitor post image as Gemini vision input — decision note

**Status:** shipped 2026-08-20 (`6e654d0`), corrected the same day — see
"What shipped, and where it differed" at the foot. The live vision call is still
unverified: Gemini answers 429 RESOURCE_EXHAUSTED until AI Studio is topped up.

## Question

Did the old app use the image from a competitor post as input? Plan: follow the
old mechanics in the new app (`fb-agent`) — the agent should read the image too.

## Old app (`D:\Laboratory\social-agent`, branch `feature/migrate-to-new-deployment`)

Yes — but only as **vision input to Gemini**, never as the output image.

- `src/services/facebookGenerateGraph.ts:464-467` (`writeThreeDraftsNode`):
  fetches the competitor post's `picture_url`, attaches it as an `inlineData`
  image Part in the same user message as the caption text. Gated to competitor
  posts only ("Only competitor posts (not saved-viral) send their image to
  Gemini"); a missing/expired image silently falls back to text-only.
- `src/lib/gemini/fetch-image-part.ts`: plain `fetch(url)` with a browser-ish
  `User-Agent` (publisher CDNs 403 anonymous requests), `<= 4MB`, mime
  `png|jpeg|jpg|webp|gif`, any failure → `null`.
- Same pattern in `src/services/facebookTopicSuggestService.ts:56`.
- Output image stayed separate: `buildFacebookImageUserPrompt` → Gemini hero →
  compositor (text panel + logo watermark) → `attachDraftImageAsync`. The
  competitor image was **never reused as the output**.

## New app state that shapes the plan

- `SourceItem` carries `image_url` for all three kinds (COMPETITOR_POST, TWEET,
  RSS); competitor rows get it from Metricool's `picture` field
  (`sources/metricool.py:107`).
- The writer is text-only today: `writer.user_prompt()` builds one string,
  `agent.run_sync(prompt)` (`writer/agent.py:206-265`). Feasibility proven:
  pydantic-ai 2.22 `run_sync` takes `str | Sequence[UserContent]`, and
  `ImageUrl`/`BinaryContent` are valid parts — `output_type=DraftContent`
  survives an image part. `usage_limits` exists for cost control.
- **Existing rule**: a competitor picture may not be *reused* — `hero_from_source`
  is RSS-only (`generate.py:283`), `source_instruction` says "reusing the image a
  rival page shot is lifting". The rule governs the **output** (hero); it never
  governs writer **input**. Reading ≠ reusing.
- Browse does not write (ADR-0001 logic): competitor posts are read live,
  `SourceItem` rows are created only when a run uses them. There is no library
  or viral path through the writer: `reuse_saved` runs as a **topic** with no
  image (`routes/overview.py:193`).

## Decisions (settled)

1. **The writer reads the competitor image as vision input**, alongside the
   caption, exactly as the old app did. Input only.
2. **Visual facts, not style.** The model may extract subject matter the caption
   alone misses (people, setting, products). It must not describe or imitate the
   rival's composition, colors, or card layout — and **`image_prompt` is guarded
   too**: the model's preferred hero prompt must not ask the hero model to
   reproduce what the competitor image looks like. That is the existing
   off-limits rule, entering through the hero channel.
3. **Gating: competitor posts only.** TWEET and RSS items also carry images;
   they stay text-only — matching both the old app's draft path and the plan.
   Broadening after measurement, not by default.
4. **Image bytes are copied at first use, not at sync.** `resolve_sources` is
   where a browsed item becomes a row; that is the moment to fetch and hold the
   bytes (repost's `copy_original_image` is nearly the same code). Browsing
   stays live-only — no mirror, no storing 100s of competitor images nobody
   ticks. If the copy fails, the run continues text-only **with a warning on
   the draft**, never silent, never a refusal. The old app's silent fallback is
   exactly the failure mode the repost work measured (0/382 links alive).
5. **Fetch mechanics** follow the old app: browser UA for CDN 403s, mime
   whitelist `png|jpeg|jpg|webp|gif`, keep 4MB cap (Gemini input ceiling;
   old code used it), any failure → warning + text-only.
6. **No fallback-model special-casing.** All models in `text_fallback_chain`
   are Gemini text models and multimodal; image parts ride the existing chain
   with no model-drop wiring.

## What the image is NOT used for

- Not the draft's output image. Hero stays generated (or RSS-source reuse, the
  existing rule) — the competitor image is input to the text writer only.

## Implementation sketch

- `writer.user_prompt` gains an optional image part slot:
  `BinaryContentDataUrl(data=..., media_type=...)` or `ImageUrl` fetched first.
- `resolve_sources` fetches + holds bytes for COMPETITOR_POST items (or
  `generate` fetches at first-use); failure → draft warning, not failure.
- One `source_instruction` addition for COMPETITOR_POST: the image is subject
  matter, the rival's layout is not to be described or reused.
- Test with the existing fake model (tests pass `model=`); assert the image part
  lands in the content and that a failed fetch still writes a draft.

## What shipped, and where it differed

Decisions 1, 2, 3 and 6 shipped as written. The rest:

- **Decision 4, first half — bytes are fetched in `_run_one`, not copied in
  `resolve_sources`, and nothing is persisted.** `resolve_sources` runs at
  `POST /generate` and `_run_one` seconds later on the background task, so the
  fetch is no staler; and nothing downstream needs the bytes a second time,
  because the hero never uses them. Persisting them would have been a column
  and a cleanup path for data with one reader.
- **Decision 4, second half — "never silent" was broken on arrival and is now
  fixed.** The warning was given the prefix `"Image: "`, which is
  `IMAGE_WARNING`, which every hero-rebuild path in `routes/drafts.py` strips
  before re-deriving from `build_image` (three call sites). One redraw, crop
  nudge or inset upload deleted the record that the writer never saw the
  rival's picture, and nothing re-derived it. Its own prefix now
  (`"Source image: "`), pinned by
  `test_the_unread_picture_warning_survives_a_redraw`.
- **Decision 5 shipped untested and is now tested.** Every run-level test
  stubs `competitor_image` wholesale, so no test touched the mime whitelist,
  the 4MB cap, the UA or the error path. `competitor_image` took a `client`
  seam (same shape as `hero.from_url`) and those bounds are driven over a
  `MockTransport`. Two gaps surfaced doing it: `image/jpg` and any
  mixed-case content-type were rejected where the old app's `/i` regex
  accepted them, and a 200 with an **empty body** became
  `BinaryImage(data=b"")` — which the model rejects, and a model error fails
  the whole draft, the one outcome decision 4 rules out. The old app checked
  for zero bytes; this now does too.
- **`rewrite` stays text-only — decided 2026-08-20, not overlooked.** `write`
  takes the image and `writer.rewrite` does not, which looked like a gap until
  the old app was checked: its regenerate sends `buildDraftContext(draft)` and
  has never sent an image (`facebookDraftRegenerateService.ts:60-111`). Only
  the initial three-draft write got vision there, so this already matches
  decision 1's "exactly as the old app did".

  The picture is not lost by leaving it out. `keeping` puts the two fields the
  operator is not replacing into the prompt verbatim, and those were written
  while the model could see the image — so its contribution to the subject is
  already in front of the call as prose. Against that, a rewrite is
  synchronous and pressed repeatedly, so sending the image would buy a CDN
  fetch and vision tokens per press, and a fetch that failed mid-session would
  need a warning channel on `RewriteProposal` that does not exist (the route
  writes nothing to the row by design — *Rewrite proposes, Save writes*).

## Follow-ups

- Cut an ADR from this note if the feature moves forward (docs/adr/0004?).
- Refreshing model-check: `gemini-3.5-flash` is a pinned id that may already rot
  (CLAUDE.md's pinned-model warning). Verify with a real vision call before
  shipping the writer change.