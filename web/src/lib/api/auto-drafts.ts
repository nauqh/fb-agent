import type { AutoDraftStatus } from "@/lib/types";
import { get } from "@/lib/api/client";

/**
 * What the automation did last, and which Pages are about to run dry.
 *
 * Every Page in one read, deliberately unscoped: the question the monitor asks
 * is "is anything wrong anywhere", which the Page switcher cannot ask.
 */
export async function getAutoDraftStatus(limit = 20): Promise<AutoDraftStatus> {
  return get<AutoDraftStatus>("/auto-drafts/status", { limit });
}
