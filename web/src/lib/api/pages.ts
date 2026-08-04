import type { Page, PromptFile } from "@/lib/types";
import { PROMPT_FILES } from "@/lib/fixtures/pages";
import { db, emit, latency, nowIso } from "@/lib/store";
import { isTodayInHoChiMinh } from "@/lib/quota";

/**
 * `GET /pages`, `GET /pages/{id}`, `PATCH /pages/{id}`.
 *
 * Swapping this file to the real API is replacing each body with a `fetch`.
 * Nothing above this line knows the difference, which is the whole point of
 * putting the seam here rather than in the components.
 */

export async function listPages(): Promise<Page[]> {
  return latency(db.pages);
}

export async function getPage(id: number): Promise<Page> {
  const page = db.pages.find((candidate) => candidate.id === id);
  if (!page) throw new Error(`No page ${id}`);
  return latency(page);
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
  const page = db.pages.find((candidate) => candidate.id === id);
  if (!page) throw new Error(`No page ${id}`);
  if (update.daily_quota !== undefined && update.daily_quota < 1) {
    throw new Error("daily_quota must be at least 1");
  }

  Object.assign(page, update, { updated_at: nowIso() });
  emit();
  return latency(page, 320);
}

/**
 * What a Page has used of today's Quota.
 *
 * Nothing publishes in v1, so Approve is what consumes Quota — see CONTEXT.md.
 * Advisory only: at or over the cap the UI warns and still lets the run go,
 * because an approved Draft can still be rejected.
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
 * The prompt files on disk.
 *
 * Read-only on purpose. They are files so that they are reviewable in git; a
 * textarea here would quietly become the place they are edited and undo that.
 */
export async function listPromptFiles(): Promise<PromptFile[]> {
  return latency(PROMPT_FILES, 120);
}
