import { ScheduleView } from "@/components/schedule-view";
import { ScreenHeader } from "@/components/screen";

/**
 * What is going out, and what already went.
 *
 * Read-only, and it will stay that way. Rescheduling and cancelling happen in
 * Metricool's planner because that is where the schedule *is* — see ADR-0001,
 * and the 0 rows the old system's mirror held in production.
 */
export default function ScheduleScreen() {
  return (
    // `overflow-hidden`, not `overflow-y-auto`: the header and the view toggle
    // stay put, and whichever view is showing owns the scrolling. The shell
    // already fixes the viewport on `lg`, so nothing here needs `sticky`.
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
      <ScreenHeader
        title="Schedule"
        // "Reschedule and cancel there" until 2026-08-18, and false since D6
        // shipped the day before: a queued post is moved and cancelled from the
        // Review drawer now, without opening Metricool. The same sentence was
        // corrected in README.md; this copy is the one an operator actually
        // reads, so it mattered more.
        hint="Live from Metricool's planner. Move or cancel a queued post from its draft in Review."
      />
      <ScheduleView />
    </div>
  );
}
