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
  watermark_image_path: string | null;
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
  text: string;
  url: string | null;
  image_url: string | null;
  published_at: string | null;
  /** Null for tweets and RSS items. */
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
  overlay_text: string | null;
  highlight_phrases: string[];
  hashtags: string[];

  image_prompt: string | null;
  hero_image_path: string | null;
  composed_image_path: string | null;

  /** Brand rules still failing after the writer exhausted its retries. */
  warnings: string[];

  progress_step: string | null;
  progress_pct: number;
  error: string | null;

  created_at: string;
  updated_at: string;
}

/**
 * Whether the *subject* binds the writer.
 *
 * Derived from `kind`, never stored — a stored copy is a second truth, and when
 * it drifts the model still returns confident, well-formed output about the
 * wrong story. Mirrors `SourceKind.is_factual` in models.py.
 */
export function isFactual(kind: SourceKind): boolean {
  return kind !== "competitor_post";
}

/** A prompt file on disk, as Settings displays it. Not a table. */
export interface PromptFile {
  filename: string;
  chars: number;
  body: string;
}
