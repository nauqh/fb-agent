import type { Page, PromptFile } from "@/lib/types";
import { del, delJson, get, patch, post, put, upload } from "@/lib/api/client";
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

  /**
   * How long this Page writes (C6, C7). **Null clears the override** and
   * returns the Page to the house numbers in `api/app/writer/validators.py` —
   * so an emptied box must send null, never 0.
   *
   * The API refuses a combination no draft could satisfy (422) rather than
   * saving it: a 1,500-character ceiling against the 1,500 house floor is not
   * a strict Page, it is a Page whose every run dies on retries.
   */
  hook_max_words?: number | null;
  first_comment_min_chars?: number | null;
  first_comment_max_chars?: number | null;
  first_comment_min_paragraphs?: number | null;
  first_comment_max_paragraphs?: number | null;
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
 * The prompts as the model is sent them.
 *
 * Served rather than bundled because the bundled copy drifted — it went on
 * listing `image_rules.txt` after that file was merged into `image.txt`.
 *
 * `pageId` resolves the overrides. Always pass it. Omitting it renders the
 * global files under a Page's name, which is the same lie the old tool's
 * Settings tab told.
 *
 * Each entry says which of three places its text came from — see
 * `PromptFile.source`.
 */
export async function listPromptFiles(pageId?: number): Promise<PromptFile[]> {
  return get<PromptFile[]>(
    pageId === undefined ? "/prompts" : `/prompts?page_id=${pageId}`,
  );
}

/**
 * Give one Page its own text for one prompt. **Blank clears the override.**
 *
 * Per Page only; there is no call that edits a global. The globals are the
 * reviewed default and live in git, and every Page reads them — editing one
 * from here is what would reopen the drift the files were chosen to prevent.
 *
 * This is stored on the Page row rather than written to
 * `api/prompts/pages/<slug>/`, and that is not a preference: Railway's
 * filesystem is ephemeral, so a written file would vanish on the next
 * redeploy — silently, days later.
 */
export async function setPromptFile(
  pageId: number,
  filename: string,
  body: string,
): Promise<PromptFile> {
  return put<PromptFile>(`/prompts/${pageId}/${filename}`, { body });
}

/**
 * When this Page publishes — the times "Schedule next available slot" walks.
 *
 * Policy, not schedule state: a slot is a standing decision that exists whether
 * or not anything is queued against it, which is why it lives here and not in
 * Metricool. See `PageTimeSlot` on the API side.
 */
export interface TimeSlot {
  id: number;
  page_id: number;
  minute_of_day: number;
  /** `HH:MM`, so a screen never does arithmetic to show a time. */
  label: string;
}

export async function listSlots(pageId: number): Promise<TimeSlot[]> {
  return get<TimeSlot[]>(`/pages/${pageId}/slots`);
}

export async function addSlot(
  pageId: number,
  hour: number,
  minute: number,
): Promise<TimeSlot> {
  return post<TimeSlot>(`/pages/${pageId}/slots`, { hour, minute });
}

export async function removeSlot(pageId: number, slotId: number): Promise<void> {
  await del(`/pages/${pageId}/slots/${slotId}`);
}
