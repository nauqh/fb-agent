import { del, get, patch } from "./client";

/**
 * The Composed Image layout for one Page.
 *
 * `config/layout.yml` holds the defaults and stays in git; a `page_layout` row
 * holds only what this Page changed. `overridden` names the columns that row
 * actually sets, which is what lets the screen mark a changed field — derived
 * from the row rather than by diffing against the defaults, because a Page that
 * deliberately sets a value *to* today's default has still overridden it and
 * would stop tracking the file if the file changed.
 *
 * Its own module rather than an addition to `api/config.ts`: that file is being
 * edited in another session, and a merge conflict in the one place both screens
 * read their configuration from is not worth the tidiness.
 */
export interface ResolvedLayout {
  /**
   * Which card form. `card` divides the height between hero and panel;
   * `full_overlay` fills the card with the hero and lays the panel over its
   * bottom, which only reads as one picture if `panel.opacity` is below 1.
   */
  template: "card" | "full_overlay";
  image: { width: number; height: number; edge_margin_ratio: number };
  panel: { ratio: number; max_ratio: number; color: string; opacity: number };
  text: {
    font_size_px: number;
    line_height_ratio: number;
    align: string;
    color: string;
    padding: {
      left_px: number;
      right_px: number;
      top_px: number;
      bottom_px: number;
    };
  };
  highlight: { color: string };
  watermark: { max_px: number; top_ratio: number };
  /** The headline chip's style. Its word is the Page's `badge_text`. */
  badge: {
    color: string;
    text_color: string;
    font_size_px: number;
    radius_px: number;
    padding_x_px: number;
    padding_y_px: number;
    gap_ratio: number;
  };
  portrait: {
    size_px: number;
    min_px: number;
    max_width_ratio: number;
    ring_pad_px: number;
    border_width_px: number;
    border_color: string;
  };
}

export interface LayoutResult {
  layout: ResolvedLayout;
  /** Column names this Page overrides. Empty means it is on the defaults. */
  overridden: string[];
}

/** The flat column names `PATCH` takes. Null clears one back to the default. */
export interface LayoutPatch {
  template?: "card" | "full_overlay" | null;
  panel_ratio?: number | null;
  panel_max_ratio?: number | null;
  panel_color?: string | null;
  panel_opacity?: number | null;
  text_font_size_px?: number | null;
  text_line_height_ratio?: number | null;
  text_align?: string | null;
  text_color?: string | null;
  text_padding_left_px?: number | null;
  text_padding_right_px?: number | null;
  text_padding_top_px?: number | null;
  text_padding_bottom_px?: number | null;
  highlight_color?: string | null;
  watermark_max_px?: number | null;
  watermark_top_ratio?: number | null;
  badge_color?: string | null;
  badge_font_size_px?: number | null;
  portrait_size_px?: number | null;
}

export async function getPageLayout(pageId?: number): Promise<LayoutResult> {
  return get<LayoutResult>("/layout", pageId ? { page_id: pageId } : undefined);
}

export async function savePageLayout(
  pageId: number,
  changes: LayoutPatch,
): Promise<LayoutResult> {
  return patch<LayoutResult>(`/layout?page_id=${pageId}`, changes);
}

/**
 * Back to `layout.yml`. Deletes the row rather than writing the defaults into
 * it, so the Page keeps tracking the file afterwards.
 */
export async function resetPageLayout(pageId: number): Promise<void> {
  await del(`/layout?page_id=${pageId}`);
}
