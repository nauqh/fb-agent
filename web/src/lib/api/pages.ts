import type { Page, PromptFile } from "@/lib/types";
import { get, patch } from "@/lib/api/client";
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
