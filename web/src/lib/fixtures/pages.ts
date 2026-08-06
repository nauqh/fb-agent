import type { Page, PromptFile } from "@/lib/types";

/**
 * The one Page.
 *
 * Values are the row `api/scripts/seed_page.py` inserts, not invented ones — v1
 * runs History Retraced only, and the watermark is a committed file under
 * `api/assets/`, recovered from the previous Supabase project after the current
 * one's copy started 404ing. It is versioned with the code that reads it so a
 * fresh clone is complete. See docs/data-model.md#layout-is-config-not-data.
 */
export const PAGES: Page[] = [
  {
    id: 1,
    name: "History Retraced",
    facebook_page_id: "569035169625026",
    metricool_blog_id: "4605385",
    avatar_image_path: "assets/pages/history-retraced.jpg",
    watermark_image_path: "assets/watermarks/history-retraced-stacked.png",
    created_at: "2026-08-03T02:10:00Z",
    updated_at: "2026-08-03T02:10:00Z",
  },
];

/**
 * The prompt files, as Settings shows them.
 *
 * Copied verbatim from `api/prompts/*.txt`. They are files precisely so that
 * they are reviewable in git rather than invisible in a column, so the UI shows
 * them and does not offer to edit them. `{panel_pct}` and `{highlight_color}`
 * are substituted from layout.yml at read time on the API side — they are left
 * unsubstituted here because that is what is on disk.
 */
export const PROMPT_FILES: PromptFile[] = [
  {
    filename: "system.txt",
    body: `Gold Standard Structure and Format for history and story posts consisting of 3 distinct parts and an Image prompt at the end.

1. The Hook: this is the text appeared on the image
* Purpose: To "stop rollers" (scroll-stoppers), grab attention, and trigger intense curiosity.
* Rules: Must be punchy, appealing, and straight to the point.
 * Must include the name and year of the event/person.
 * Punchy, appealing, straight to the point, and triggers curiosity.
 * Strictly under 65 words.
 * No asking questions.

2. The Recap: this is the caption of the post
* Purpose: A short-form storytelling overview that hits the most interesting points to make readers want to explore further (by tapping the first comment aka the main body).
* Rules: Uses a storytelling approach rather than just a dry chronological list of events.
 * A related, descriptive emoji must be placed in front of each point.
 * Do not use confusing "verb+ing" sentence starters (keep a clear grammatical subject).
 * Maximum of 5 points.

3. The Main Body: this is the First Comment under the post
* Purpose: The complete, in-depth background story that extends the details introduced in the hook and recap, giving readers the full picture.
* Rules: Every character mentioned must have their birth and death year included.
 * If a person is still alive, use the format: Jane Doe (b. 19xx).
 * Highly scannable, concise, and tightly paced (ideally between 1,800 to 1,900 characters max).
 * Strictly omit meta-phrases like "2026 look back", "as of today...", or "as we look back...".

4. The Image Prompt:
* When requested, a highly detailed, cinematic 8k square image prompt is placed at the very end to visually capture the historical scene in a photorealistic style.
`,
  },
  {
    filename: "overlay.txt",
    body: `Image text panel (composited in post-processing — not drawn by the image model):

The hook is what goes on the panel. It is defined above; nothing is restated
here, because this file used to carry a second copy of its rules under a second
field name and the two drifted.

highlightPhrases (gold highlights on the text panel):
* Return 5-8 exact substrings copied verbatim from the hook (never fewer than 5).
* Use short phrases (1-4 words each): years, numbers with units, names, places — e.g. "690 AD", "only female Emperor", "ruthless rise" as separate entries.
* Do NOT use one long clause as a single highlight; split into multiple short phrases.
* Keep each phrase short enough to sit on one line. The panel wraps at roughly 45 characters, and a phrase broken across two lines renders no gold at all.

Visual rendering (added in code — for your awareness only):
* Black panel, white body text, gold ({highlight_color}) on highlightPhrases, bold sans-serif, centered.
`,
  },
  {
    filename: "image.txt",
    body: `You generate the top hero photograph for a History Retraced Facebook post card.

Visual style — MANDATORY:
- 100% photorealistic photograph. It must look like a real photo from a camera, NOT illustration or digital painting.
- Mid-shot / medium close-up with a clear focal face or figure in the foreground.
- Documentary or cinematic historical reenactment photography: believable environment (battlefield, city, interior, landscape).
- Dramatic but natural lighting (golden hour, overcast, torchlight); no neon, no magic glow, no fire heads, no supernatural effects.
- One grounded historical moment — factual tone, not fantasy or surreal symbolism.

Final post card assembly (layers 2—3 are added in code — do NOT draw them):
1. HERO PHOTO (top portion — shrinks when copy is long) — YOU generate only this: full-bleed photorealistic photograph, square output, no UI, no text.
2. BLACK TEXT BOX (bottom, at least ~{panel_pct}% of card height, grows to fit copy) — solid black panel with white/gold copy (added in code).
3. BRAND LOGO — uploaded brand logo (natural aspect ratio), top-right corner of the hero (added in code). Leave top-right empty in your photo.

Your output must be layer 1 only — a clean photograph with zero text and zero logos.

Hero composition rules:
- Full-bleed photorealistic photograph edge to edge — no letterboxing or post mockup.
- Must look like a real camera photo (documentary, editorial, or historical reenactment photography).
- COMPOSITION: mid-shot or medium close-up — main subjects fill ~40–60% of frame height (~50% larger than a wide panorama). Not tiny distant figures.
- FOCAL POINT: 1–3 faces or figures clearly visible in the foreground as the visual hook (reenactment faces OK). Prefer subjects facing or near the camera.
- When people appear: believable anatomy and period-accurate dress; faces must be readable at feed size.
- Keep the entire top-right quadrant clean — a brand logo is composited there in post.
- NO surreal metaphors (giant objects, glowing silhouettes, fantasy props, comic or illustrated style).

Strict exclusions — your image must contain NONE of these:
- ANY readable text, letters, numbers, captions, titles, headline typography, or hashtags (including #tags painted in the image)
- ANY social-media post mockup: black bars, text panels, meme layout, or card framing
- ANY brand names, logos, watermarks, or channel name text
- Black text box, speech bubbles, UI chrome, or post mockup frames
- Circular frames, medallions, round profile photos, or logo badges drawn in the photo
- Digital illustration, cartoon, anime, 3D render, or "AI art" look — photograph only
- Wide establishing shots where people are small specks in the distance
`,
  },
].map((file) => ({ ...file, chars: file.body.length }));

/**
 * The Composed Image constants the preview has to agree with.
 *
 * Mirrors `api/config/layout.yml`. The preview is a CSS approximation — browser
 * text metrics are not fontTools advance widths — so these govern proportion,
 * not pixels.
 */
export const LAYOUT = {
  width: 896,
  height: 1120,
  panelRatio: 0.2,
  panelMaxRatio: 0.85,
  panelColor: "#000000",
  textColor: "#ffffff",
  highlightColor: "#F5C542",
  fontSizePx: 36,
  lineHeightRatio: 1.26,
  edgeMarginRatio: 0.02,
  /** Watermark width cap. Capped again at 0.22 × width by the compositor. */
  watermarkMaxPx: 138,
} as const;
