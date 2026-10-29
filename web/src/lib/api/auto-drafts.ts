import type { AutoDraftStatus } from "@/lib/types";
import { get, post } from "@/lib/api/client";

/**
 * What the automation did last, and which Pages are about to run dry.
 *
 * Every Page in one read, deliberately unscoped: the question the monitor asks
 * is "is anything wrong anywhere", which the Page switcher cannot ask.
 */
export async function getAutoDraftStatus(days = 7): Promise<AutoDraftStatus> {
  return get<AutoDraftStatus>("/auto-drafts/status", { days });
}

/**
 * Run this Page now, whatever its configured times say. Returns the new draft
 * ids; an empty list means it ran and found nothing left to write about.
 *
 * The scheduled path is `/generate/auto/due`, which the cron calls. This is the
 * operator's button, so it also works when no times are set.
 */
export async function runAutoDraft(pageId: number): Promise<number[]> {
  return post<number[]>("/generate/auto", {
    page_ids: [pageId],
    hero_from_source: false,
  });
}
