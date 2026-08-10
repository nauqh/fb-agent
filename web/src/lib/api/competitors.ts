import { del, get, post, put } from "./client";

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

/** How much of Metricool's competitor limit is spent, across the whole account. */
export interface Allowance {
  used: number;
  limit: number;
  remaining: number;
  /** Every brand on the account, not just the ones this app manages. */
  profiles: {
    blog_id: string;
    label: string;
    competitors: number;
    managed: boolean;
  }[];
}

/**
 * Costs one request per brand, so it is its own call — the competitor list
 * should not wait several seconds for a number beside it.
 *
 * Counts every brand deliberately. Measured while this was written: 92 of 100
 * in use, and 44 of those sat on brands with no Page in this app. Counting only
 * what this app manages would have shown 48 and implied 52 slots free, when
 * there were 8.
 */
export async function getAllowance(): Promise<Allowance> {
  return get<Allowance>("/competitors/allowance");
}

/**
 * Start watching a Facebook page. Writes to Metricool, stores nothing here.
 *
 * `pageId` only decides which brand's set it lands in — where the allowance is
 * spent — not who may read it. Any Page can then be assigned it.
 */
export async function addToPool(pageId: number, facebookPageId: string): Promise<void> {
  await post<{ added: string }>("/competitors", {
    page_id: pageId,
    facebook_page_id: facebookPageId,
  });
}

/** `competitorId` is Metricool's own row id, not the Facebook page id. */
export async function removeFromPool(competitorId: number, pageId: number): Promise<void> {
  await del(`/competitors/${competitorId}?page_id=${pageId}`);
}
