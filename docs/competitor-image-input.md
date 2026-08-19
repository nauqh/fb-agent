# Competitor post image as Gemini vision input — decision note

**Status:** decision settled under grilling (2026-08-19). Not implemented.

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

## Follow-ups

- Cut an ADR from this note if the feature moves forward (docs/adr/0004?).
- Refreshing model-check: `gemini-3.5-flash` is a pinned id that may already rot
  (CLAUDE.md's pinned-model warning). Verify with a real vision call before
  shipping the writer change.