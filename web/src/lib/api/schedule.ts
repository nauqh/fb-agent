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

/**
 * The next configured publishing time this Page has free.
 *
 * Computed on the server against Metricool's planner, never against local
 * state — a post somebody scheduled by hand in Metricool's own UI occupies a
 * slot exactly as much as one of ours (ADR-0001).
 */
export interface NextSlot {
  /** Naive local time in the Page's zone, as publish takes it. */
  when: string;
  /** `HH:MM`, the slot as configured. */
  label: string;
  /** Slots skipped because the planner already had a post at them. */
  taken: number;
}

export async function getNextSlot(pageId: number): Promise<NextSlot> {
  return get<NextSlot>("/schedule/next-slot", { page_id: pageId });
}
