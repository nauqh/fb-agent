import type { Page, PromptFile } from "@/lib/types";
import { get, patch } from "@/lib/api/client";
import { db, latency } from "@/lib/store";
import { isTodayInHoChiMinh } from "@/lib/quota";

/**
 * `GET /pages`, `GET /pages/{id}`, `PATCH /pages/{id}`, `GET /prompts`.
 *
 * `getQuotaUsage` is the one thing still counted against the fixture store,
 * because what it counts is Drafts — and `GET /drafts` arrives with Phase 3.
 * It is marked below rather than left to be discovered.
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
  daily_quota?: number;
  watermark_image_path?: string | null;
}

export async function updatePage(id: number, update: PageUpdate): Promise<Page> {
  // The server enforces this too (422). Checked here as well so the operator is
  // told before a round trip, not after one.
  if (update.daily_quota !== undefined && update.daily_quota < 1) {
    throw new Error("daily_quota must be at least 1");
  }
  return patch<Page>(`/pages/${id}`, update);
}

/**
 * What a Page has used of today's Quota.
 *
 * Nothing publishes in v1, so Approve is what consumes Quota — see CONTEXT.md.
 * Advisory only: at or over the cap the UI warns and still lets the run go,
 * because an approved Draft can still be rejected.
 *
 * **Still the fixture store.** Counting approved Drafts needs `GET /drafts`,
 * which Phase 3 builds; until then this number is honest about the prototype's
 * drafts and not about anything on disk.
 */
export async function getQuotaUsage(pageId: number): Promise<number> {
  const used = db.drafts.filter(
    (draft) =>
      draft.page_id === pageId &&
      draft.status === "approved" &&
      isTodayInHoChiMinh(draft.updated_at),
  ).length;
  return latency(used, 60);
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
