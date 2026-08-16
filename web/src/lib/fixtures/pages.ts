import type { Page } from "@/lib/types";

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
    // No committed avatar any more: the logo comes from Metricool, which serves
    // the Facebook profile picture and follows it when it changes.
    avatar_image_path: null,
    avatar_url: "https://static.metricool.com/brand/facebook-page-image?brandId=4605385",
    watermark_image_path: "assets/watermarks/history-retraced-stacked.png",
    // This Page's mark is the committed file, so it has no upload. The eight
    // Pages with no asset in the repo are the ones the upload exists for.
    watermark_upload_path: null,
    watermark_upload_url: null,
    // Null means the Page's name, and this Page draws its committed asset
    // anyway — the text is only reached when there is no image at all.
    watermark_text: null,
    watermark_enabled: true,
    // History Retraced draws the `card` template, which has no headline chip.
    badge_text: null,
    // All null, and that is the seeded row rather than a gap in the fixture.
    // Null means "the house number" — 65 words, 1,500–2,100 characters, 2–3
    // paragraphs — and History Retraced is the Page those numbers were written
    // for. The two Pages that asked for their own are Bodybuilding Tips and
    // Fitness Recipes (C6, C7).
    hook_max_words: null,
    first_comment_min_chars: null,
    first_comment_max_chars: null,
    first_comment_min_paragraphs: null,
    first_comment_max_paragraphs: null,
    // Likewise: no stored prompt means the files in `api/prompts/` are what
    // this Page is sent, which is what they were written for.
    system_prompt: null,
    overlay_prompt: null,
    image_prompt: null,
    created_at: "2026-08-03T02:10:00Z",
    updated_at: "2026-08-03T02:10:00Z",
  },
];

/**
 * `PROMPT_FILES` used to live here: a hand-kept copy of `api/prompts/*.txt`,
 * with no consumers left once the screen moved to `GET /prompts`.
 *
 * It is gone rather than kept in sync, for the reason the API-side docstring
 * gives at length: a second copy of a prompt is the failure mode this project
 * has already paid for twice. This one had drifted too — it never grew the
 * Accuracy block — and per-Page prompts under `prompts/pages/<slug>/` would
 * have made it wrong for two more Pages the moment they landed.
 */

/**
 * `LAYOUT` used to live here: a hand-kept copy of `api/config/layout.yml`, with
 * no per-Page values in it because it predates `page_layout`.
 *
 * It is gone rather than kept in sync. `ComposedImage` and the drawer's inset
 * slider now read `GET /layout`, which is the resolved layout — the file's
 * defaults with the Page's overrides laid over them, the same object
 * `layout_for.resolve` hands the compositor. Nothing on this side of the wire
 * should hold a second copy of those numbers; that copy is what made every
 * padding and type-size override on Global invisible on the Review screen.
 */
