/**
 * The three tables, as the API returns them.
 *
 * These mirror `api/app/models.py` field for field, because SQLModel table
 * classes are also the API-facing types — there is no second set of DTOs on the
 * Python side, so there should not be one here either. Dates arrive as ISO
 * strings over JSON and stay strings; nothing in the UI does date arithmetic —
 * they are only ever formatted, in `lib/format.ts`.
 */

export type SourceKind = "competitor_post" | "tweet" | "rss";

/** `failed` means the run produced nothing; `error` says why. Never in `review`. */
export type DraftStatus =
  | "generating"
  | "review"
  | "approved"
  | "rejected"
  | "failed";

/** An owned Facebook page. v1 has exactly one: History Retraced. */
export interface Page {
  id: number;
  name: string;
  facebook_page_id: string;
  metricool_blog_id: string | null;
  /**
   * The Page's logo file, relative to `API_DIR` — a committed asset under
   * `api/assets/`, not storage. Null is an error state, not a fallback: the old
   * compositor treated a missing file as "no logo" and printed the name as text,
   * and the logo vanished from output for months without one failed post.
   */
  avatar_image_path: string | null;
  /** Metricool's brand logo. Fallback for Pages with no committed asset. */
  avatar_url: string | null;
  watermark_image_path: string | null;
  /**
   * An uploaded mark, bucket-relative. Wins over the committed asset when set,
   * and is the answer for the eight Pages whose artwork is not in the repo.
   */
  watermark_upload_path: string | null;
  /** The uploaded mark's public URL. Null when the Page is on a committed asset. */
  watermark_upload_url: string | null;
  /**
   * What is printed when there is no image mark at all. Null means the Page's
   * `name` — which is the Metricool brand name, and not always something to
   * stamp on a photograph ("GYM Motivation | quotes | videos | tips|").
   */
  watermark_text: string | null;
  /**
   * Whether this Page's cards get a mark at all. False publishes the
   * photograph clean — no image *and* no fallback text.
   */
  watermark_enabled: boolean;
  /**
   * The headline chip's word — "NEWS", "HISTORY". Null draws no chip, and it is
   * drawn on `full_overlay` cards only, where the panel lies over the
   * photograph and there is room above it.
   */
  badge_text: string | null;

  /**
   * How long this Page writes. **Null means the house number**, not zero —
   * 65 words, 1,500–2,100 characters, 2–3 paragraphs, from
   * `api/app/writer/validators.py`.
   *
   * Nullable rather than defaulted so a chosen value can be told from a copied
   * one: with defaults, changing the house number would leave every Page pinned
   * to the old one with nothing recording that anybody meant it.
   */
  hook_max_words: number | null;
  first_comment_min_chars: number | null;
  first_comment_max_chars: number | null;
  first_comment_min_paragraphs: number | null;
  first_comment_max_paragraphs: number | null;

  /** This Page's own prompt text, or null to inherit the file. Edited through
   *  `setPromptFile`, and read back through `listPromptFiles`. */
  system_prompt: string | null;
  overlay_prompt: string | null;
  image_prompt: string | null;

  created_at: string;
  updated_at: string;
}

/** External material selected as input. One shape, three kinds. */
export interface SourceItem {
  id: number;
  kind: SourceKind;
  external_id: string;
  /** Competitor page name, X handle, or publisher. */
  author: string | null;
  /** competitor_post only. */
  synced_for_page_id: number | null;
  /**
   * The competitor's Facebook page id. competitor_post only.
   *
   * What the grid is filtered by — a Page reads the posts whose competitor it
   * has ticked — and what `competitorAvatar` turns into a logo.
   */
  competitor_page_id: string | null;
  text: string;
  url: string | null;
  image_url: string | null;
  published_at: string | null;
  /** Null for tweets and RSS items. */
  /** A Draft already came from this one. Server-derived, competitor posts only. */
  used?: boolean;
  reactions: number | null;
  comments: number | null;
  shares: number | null;
  created_at: string;
}

/**
 * A generated post awaiting review.
 *
 * The row exists before generation starts, so it doubles as the job record —
 * that is why `progress_step`, `progress_pct` and `error` are here rather than
 * in an event table.
 */
export interface Draft {
  id: number;
  page_id: number;
  /** Null means the Draft came from a topic rather than a Source Item. */
  source_item_id: number | null;
  topic: string | null;
  status: DraftStatus;

  hook: string | null;
  caption: string | null;
  first_comment: string | null;
  highlight_phrases: string[];

  image_prompt: string | null;
  hero_image_path: string | null;
  composed_image_path: string | null;

  /** The uploaded circular inset. Null is the normal case — no circle. */
  inset_image_path: string | null;

  /**
   * Where each of the three paths above actually resolves, as a public Supabase
   * URL. Computed server-side and sent on every Draft — the row stores a
   * bucket-relative path so that moving project or bucket is an env change
   * rather than an UPDATE over the table, and nothing here needs to know that.
   *
   * Null exactly when the matching `_path` is null. Use `_path` to ask *whether*
   * there is a picture and `_url` to show one; a `_url` is not a stable
   * identity, since the same picture can be served from a different bucket.
   */
  hero_image_url: string | null;
  composed_image_url: string | null;
  inset_image_url: string | null;
  /** Its diameter. Null takes the default from `layout.yml`. */
  inset_size_px: number | null;
  /**
   * Its centre, as fractions of card width and height. Null is not 0 — it means
   * the default, which is the seam, and the seam moves with the panel height.
   */
  inset_x_ratio: number | null;
  inset_y_ratio: number | null;
  /**
   * The ring around the disc. Null on either means the Page's layout decides.
   *
   * Null and `0` are different answers for the width: null tracks whatever the
   * Page is set to, `0` is this draft choosing to have no ring at all.
   */
  inset_border_width_px: number | null;
  inset_border_color: string | null;
  /**
   * Whether the hero came from the Source Item's own picture rather than from
   * Gemini. Stored rather than derived, so a rebuild takes the path the run
   * took.
   */
  hero_from_source: boolean;
  /** `card` or `full_overlay` for this draft alone. Null follows the Page. */
  template: "card" | "full_overlay" | null;
  /** Text only, on purpose — distinct from a picture that failed to draw. */
  no_image: boolean;

  /** Brand rules still failing after the writer exhausted its retries. */
  warnings: string[];

  /**
   * What Metricool called the post it queued, or null if it was never pushed.
   * There is no scheduled time beside it — Metricool's planner owns that.
   */
  metricool_post_id: string | null;

  progress_step: string | null;
  progress_pct: number;
  error: string | null;

  created_at: string;
  updated_at: string;
}

/** A prompt file on disk, as Settings displays it. Not a table. */
export interface PromptFile {
  filename: string;
  chars: number;
  body: string;
  /**
   * True when this Page has its own copy under `api/prompts/pages/<slug>/`.
   *
   * The screen has to say so. A Page with its own prompts, shown the global
   * body unmarked, is a window reporting the opposite of what the model is
   * sent — which is the state the old tool shipped in for six weeks.
   */
  overridden: boolean;

  /**
   * Which of the three places the text came from: `"page"` (stored on the Page
   * row, editable here), `"file-override"` (`api/prompts/pages/<slug>/`) or
   * `"global"` (`api/prompts/`).
   *
   * `overridden` alone cannot answer what the operator is about to do. Editing
   * text that is in fact inherited creates an override nobody asked for, and a
   * file-backed one cannot be edited from a browser at all.
   */
  source: "page" | "file-override" | "global";

  /** False for a prompt with no column behind it — it can only be a file. */
  editable: boolean;
}

/**
 * One row of Metricool's planner.
 *
 * Not a `Draft`, and not stored anywhere: most of these were queued by the old
 * system, which is still what publishes History Retraced. Mapping them onto our
 * own model would invent a `hook` and `highlight_phrases` for a post somebody
 * wrote in Metricool's composer.
 */
export interface ScheduledPost {
  id: string;
  /** Naive local time, as the planner stores it — never converted to UTC. */
  published_at: string;
  timezone: string;
  text: string;
  first_comment: string | null;
  image_url: string | null;
  network: string;
  /** Metricool's word: `PUBLISHED`, `PENDING`, `ERROR`, `DRAFT`. */
  status: string;
  public_url: string | null;
  is_draft: boolean;
  /** Ours, when the post came from this app. Null for everything else. */
  draft_id: number | null;
}
