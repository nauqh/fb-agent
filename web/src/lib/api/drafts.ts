import type { Draft, DraftStatus } from "@/lib/types";
import type { LiveSourceItem } from "@/lib/api/sources";
import { get, patch, post } from "@/lib/api/client";

/**
 * `POST /generate`, `GET /drafts`, `GET /drafts/{id}`, `PATCH /drafts/{id}`,
 * approve · unapprove · reject.
 *
 * The two image routes are declared at the bottom but not yet served.
 */

export interface DraftFilter {
  /** `"all"` means every status — the server takes no filter rather than one. */
  status?: DraftStatus | "all";
  page_id?: number;
}

export async function listDrafts(filter: DraftFilter = {}): Promise<Draft[]> {
  const params: Record<string, string | number> = {};
  if (filter.status && filter.status !== "all") params.status = filter.status;
  if (filter.page_id !== undefined) params.page_id = filter.page_id;
  return get<Draft[]>("/drafts", params);
}

export async function getDraft(id: number): Promise<Draft> {
  return get<Draft>(`/drafts/${id}`);
}

/**
 * Operator edits. The written fields only; status moves through its own routes.
 *
 * `image_prompt` is in here because it is the only lever on a hero the model
 * refused — the writer produced it, so the operator has to be able to correct it
 * before paying for another generation.
 */
export type DraftEdit = Partial<
  Pick<
    Draft,
    | "hook"
    | "caption"
    | "first_comment"
    | "highlight_phrases"
    | "hashtags"
    | "image_prompt"
  >
>;

export async function updateDraft(id: number, edit: DraftEdit): Promise<Draft> {
  return patch<Draft>(`/drafts/${id}`, edit);
}

export async function approveDraft(id: number): Promise<Draft> {
  return post<Draft>(`/drafts/${id}/approve`, {});
}

export async function rejectDraft(id: number): Promise<Draft> {
  return post<Draft>(`/drafts/${id}/reject`, {});
}

/**
 * `POST /drafts/{id}/unapprove` — undo, for the toast.
 *
 * Approve is reversible right up until the v2 Metricool push, which is exactly
 * why nothing downstream may treat Approve as final: an approved Draft can come
 * back.
 */
export async function returnToReview(id: number): Promise<Draft> {
  return post<Draft>(`/drafts/${id}/unapprove`, {});
}

export interface GenerateRequest {
  /**
   * The Source Items to write from, **by value**.
   *
   * Generate is the only thing that writes a `source_item` row, so it takes the
   * item rather than an id — see docs/plan.md, "Ticking stops writing". The
   * server decides which kinds the client may author: an RSS item is host-checked
   * against the curated feeds, and a competitor post must already exist, because
   * the Metricool sync owns those rows.
   */
  sources: LiveSourceItem[];
  page_ids: number[];
  /** Set instead of sources for a topic-only run. */
  topic?: string;
}

/**
 * The run.
 *
 * Returns draft ids immediately at 202: the rows exist at `status='generating'`
 * and a background task fills them in, so the client polls `getDraft` until the
 * status moves. One real draft takes 45-130 seconds depending on how loaded the
 * model is — which is why this is a poll and not a wait.
 */
export async function generate(request: GenerateRequest): Promise<number[]> {
  return post<number[]>("/generate", request);
}

/**
 * The two image routes. One endpoint, and the flag is the whole difference.
 *
 * `recomposite` redraws over the hero already on disk and costs nothing, so it
 * is the button an operator can press after every edit. `regenerateHero` buys a
 * new picture — the only call in the app that spends money on demand, which is
 * why it is a separate function rather than an option on the first.
 */
export async function recomposite(id: number): Promise<Draft> {
  return post<Draft>(`/drafts/${id}/image`, {});
}

export async function regenerateHero(id: number): Promise<Draft> {
  return post<Draft>(`/drafts/${id}/image?new_hero=true`, {});
}
