import { get, put } from "./client";

/**
 * Which Competitors feed which Pages.
 *
 * Ours, not Metricool's — the competitor *list* is still theirs and still read
 * live (`getCompetitorPages`). What is stored is an assignment they have no way
 * to express: one competitor serving several of our Pages.
 *
 * It exists because of a hard limit. A Metricool account may configure 100
 * competitors in **total**, not per page, so five Pages that should each watch
 * the same twenty sources cannot each be given them. The source is added once,
 * under whichever Page had room, and assigned here to every Page that reads it.
 *
 * Until a Page has any assignment it falls back to the competitor set it owns
 * in Metricool, so an untouched Page behaves exactly as it always did.
 */
export interface Assignment {
  id: number;
  page_id: number;
  /** Metricool's `providerId` — the join key, never the display name. */
  competitor_page_id: string;
  name: string | null;
  /** Why this Page reads it. A table has no history; this is the compensation. */
  note: string | null;
}

export async function getAssignments(pageId: number): Promise<Assignment[]> {
  return get<Assignment[]>("/competitors/assignments", { page_id: pageId });
}

/**
 * Replace this Page's assignments with the set given.
 *
 * A whole set, not add/remove: a checkbox list *is* a set, and sending it whole
 * makes the request idempotent — two clicks racing end at the state the second
 * described rather than at whichever order the deltas arrived in.
 *
 * Omitting `notes` keeps the notes already stored, so a bare tick list cannot
 * erase the reasoning as a side effect.
 */
export async function setAssignments(
  pageId: number,
  competitorPageIds: string[],
  names: Record<string, string> = {},
  notes: Record<string, string> = {},
): Promise<Assignment[]> {
  return put<Assignment[]>(`/competitors/assignments?page_id=${pageId}`, {
    competitor_page_ids: competitorPageIds,
    names,
    notes,
  });
}
