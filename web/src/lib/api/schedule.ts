import type { ScheduledPost } from "@/lib/types";
import { get } from "@/lib/api/client";

/**
 * Metricool's planner, read live.
 *
 * There is no local schedule table to read instead, and that is ADR-0001 rather
 * than a gap: posts are scheduled, moved and cancelled in Metricool — sometimes
 * by hand, in Metricool's own UI — so a mirror could only ever be out of date.
 * The cost is that this screen needs the network and is empty when Metricool is
 * unreachable, which is the honest failure.
 */
export async function getSchedule(
  pageId: number,
  daysBack = 7,
  daysAhead = 30,
): Promise<ScheduledPost[]> {
  return get<ScheduledPost[]>("/schedule", {
    // Required, not defaulted. The server defaults it to 1 so a curl works, but
    // a planner belongs to one Metricool blog and this screen shows whichever
    // Page the switcher is on — a silent default here would show History
    // Retraced's queue under The Fact Feed's name.
    page_id: pageId,
    days_back: daysBack,
    days_ahead: daysAhead,
  });
}
