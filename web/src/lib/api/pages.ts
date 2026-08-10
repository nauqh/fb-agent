import type { Page, PromptFile } from "@/lib/types";
import { delJson, get, patch, upload } from "@/lib/api/client";
/**
 * `GET /pages`, `GET /pages/{id}`, `PATCH /pages/{id}`, `GET /prompts`.
 *
 * Every call here reaches the API. The fixture store was still backing the
 * Quota count; that went with the Quota.
 */

export async function listPages(): Promise<Page[]> {
  return get<Page[]>("/pages");
}

export async function getPage(id: number): Promise<Page> {
  return get<Page>(`/pages/${id}`);
}

/**
 * Identity is deliberately not editable: `name`, `facebook_page_id` and
 * `metricool_blog_id` come from Metricool and are not the operator's to change.
 * Mirrors `PageUpdate` in api/app/routes/pages.py.
 */
export interface PageUpdate {
  watermark_image_path?: string | null;
  /** Null clears it back to the Page's name rather than to nothing. */
  watermark_text?: string | null;
  /** False publishes clean: no image mark and no fallback text either. */
  watermark_enabled?: boolean | null;
  /** The headline chip's word. Null draws no chip. `full_overlay` only. */
  badge_text?: string | null;
}

/**
 * No screen calls this. It stays because `watermark_image_path` is the one
 * per-page value that can be wrong, and Phase 4 is the code that reads it — a
 * Page pointing at a missing logo needs a way back that is not a SQL prompt.
 */
export async function updatePage(id: number, update: PageUpdate): Promise<Page> {
  return patch<Page>(`/pages/${id}`, update);
}

/**
 * Give a Page a watermark without committing a file to the repo.
 *
 * Eight of the ten Pages have no committed asset and publish unmarked. Their
 * artwork is not in git, so the upload is the only route they have. The API
 * re-encodes to PNG keeping the alpha — the mark is white ink for a
 * photograph, and flattened it is a white wordmark on a white box.
 */
export async function uploadWatermark(id: number, file: File): Promise<Page> {
  return upload<Page>(`/pages/${id}/watermark`, file);
}

/** Drop the upload. The Page falls back to its committed asset, or to none. */
export async function removeWatermark(id: number): Promise<Page> {
  return delJson<Page>(`/pages/${id}/watermark`);
}

/**
 * Where the browser fetches this Page's mark, or null when it has none.
 *
 * Two sources with one answer: an uploaded mark is a public bucket URL, and a
 * committed asset is served by the API's own `/assets` mount — which is behind
 * the API key, and reachable only because `proxy.ts` attaches it to everything
 * under `/api`. A bare `<img src="/assets/...">` would 401.
 */
export function watermarkUrl(page: Page): string | null {
  if (page.watermark_upload_url) return page.watermark_upload_url;
  return page.watermark_image_path ? `/api/${page.watermark_image_path}` : null;
}

/**
 * The prompt files on disk, as the API reads them.
 *
 * Read-only on purpose. They are files so that they are reviewable and
 * revertable in git; a textarea here would quietly become the place they are
 * edited and undo that.
 *
 * Served rather than bundled because the bundled copy drifted — it went on
 * listing `image_rules.txt` after that file was merged into `image.txt`.
 */
export async function listPromptFiles(): Promise<PromptFile[]> {
  return get<PromptFile[]>("/prompts");
}
