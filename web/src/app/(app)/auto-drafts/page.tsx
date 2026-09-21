"use client";

import { useSyncExternalStore } from "react";

import { Loading } from "@/components/loading";
import { QueryError } from "@/components/query-error";
import { ScreenHeader } from "@/components/screen";
import { StatusPill, type StatusTone } from "@/components/status-pill";
import { getAutoDraftStatus } from "@/lib/api/auto-drafts";
import { asUtc, fullDate, timeAgo } from "@/lib/format";
import type { AutoDraftPage, AutoDraftStatus } from "@/lib/types";
import { useQuery } from "@/lib/use-query";
import { cn } from "@/lib/utils";

/**
 * Is the automation working, and is anything about to run dry.
 *
 * Deliberately **not** scoped to the selected Page. Every other screen answers
 * a question about one Page; this one answers "is anything wrong anywhere",
 * which the switcher cannot ask - an operator running seven automated Pages
 * would have to click through all seven to find the empty one.
 *
 * Three questions, in the order they are asked: did it run, what did it make,
 * and who is running out of material. Anything that is not one of those is a
 * level down, in the runs list.
 */

const RUN_HOUR_UTC = 11;
/**
 * When the cron fires. 11:00 UTC is 18:00 in Ho Chi Minh City, which has no
 * DST. **The schedule itself lives in `.github/workflows/auto-drafts.yml`** and
 * this is a copy of it, which is the honest cost of the schedule living outside
 * the app: change one and the other is wrong. Nothing enforces the pair.
 */

const STALE_AFTER_HOURS = 26;
/**
 * How long without a run before the automation is treated as stopped.
 *
 * A little over a day rather than exactly one: GitHub runs scheduled workflows
 * late often enough - ten to thirty minutes is ordinary - that a 24h threshold
 * would cry wolf on a perfectly healthy night.
 */

function nextRun(now: Date): Date {
  const next = new Date(now);
  next.setUTCHours(RUN_HOUR_UTC, 0, 0, 0);
  if (next <= now) next.setUTCDate(next.getUTCDate() + 1);
  return next;
}

/** `4h 12m`. Deliberately not seconds - nothing here is worth a ticking digit. */
function until(target: Date, now: Date): string {
  const minutes = Math.max(0, Math.round((target.getTime() - now.getTime()) / 60_000));
  const hours = Math.floor(minutes / 60);
  return hours > 0 ? `${hours}h ${minutes % 60}m` : `${minutes}m`;
}

/**
 * What a Page's remaining pool means.
 *
 * Three states, not a number with a colour: "no competitors" is a Settings
 * problem and "none left this week" is a dry spell, and they are both zero.
 * Telling them apart is the entire reason `assigned_competitors` is on the
 * response.
 */
function pool(page: AutoDraftPage): { tone: StatusTone; label: string; detail?: string } {
  if (page.assigned_competitors === 0) {
    return {
      tone: "neutral",
      label: "No competitors",
      detail: "Tick competitors for this Page on Settings before automating it.",
    };
  }
  if (page.available === 0) {
    return {
      tone: "negative",
      label: "Nothing left",
      detail: "Every post in the window has been written about already.",
    };
  }
  if (page.available <= 5) {
    return { tone: "waiting", label: "Running low" };
  }
  return { tone: "positive", label: "Ready" };
}

export default function AutoDraftsScreen() {
  const { data, error } = useQuery<AutoDraftStatus>(
    () => getAutoDraftStatus(20),
    [],
    {
      cacheKey: "auto-draft-status",
      // A run happens once a day and takes minutes. Polling faster than this
      // would be watching a kettle.
      intervalMs: 60_000,
    },
  );

  const now = useMinuteClock();

  if (error) return <QueryError error={error} />;
  if (!data) return <Loading label="Reading the automation" className="h-72" />;

  const latest = data.runs[0] ?? null;
  // `now` is null on the server and on the first paint, because a clock read
  // during render is a hydration mismatch waiting to happen.
  const stale =
    now !== null &&
    latest !== null &&
    (now.getTime() - asUtc(latest.created_at).getTime()) / 3_600_000 > STALE_AFTER_HOURS;

  // One run writes a row per Page, microseconds apart, so the batch is a time
  // window rather than an equal timestamp. Ten minutes is far longer than a
  // run takes to record its rows and far shorter than a day between runs.
  const BATCH_MINUTES = 10;
  const lastDrafts = latest
    ? data.runs
        .filter(
          (run) =>
            asUtc(latest.created_at).getTime() - asUtc(run.created_at).getTime() <
            BATCH_MINUTES * 60_000,
        )
        .reduce((sum, run) => sum + run.drafts_created, 0)
    : 0;

  const attention = data.pages.filter(
    (page) => page.assigned_competitors > 0 && page.available <= 5,
  );

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-6 overflow-y-auto pb-10">
      <ScreenHeader
        title="Auto-drafts"
        hint="Runs once a day and writes drafts into Review. Every Page, not just the selected one."
        // Off: this screen is about all Pages at once, so a Page name in the
        // title row would claim a scope it does not have. Same reasoning as
        // Global.
        switcher={false}
      />

      <div className="grid shrink-0 gap-3 sm:grid-cols-3">
        <Tile
          label="Next run"
          value={now ? `in ${until(nextRun(now), now)}` : "-"}
          detail="18:00 Vietnam time, daily"
        />
        <Tile
          label="Last run"
          value={
            latest
              ? `${lastDrafts} draft${lastDrafts === 1 ? "" : "s"}`
              : "Never run"
          }
          detail={latest ? timeAgo(latest.created_at) : "No run has been recorded yet"}
          tone={stale ? "negative" : undefined}
        />
        <Tile
          label="Needs attention"
          value={attention.length === 0 ? "All clear" : `${attention.length} Page${attention.length === 1 ? "" : "s"}`}
          detail={
            attention.length === 0
              ? "Every automated Page has material left"
              : attention.map((page) => page.page_name).join(", ")
          }
          tone={attention.length === 0 ? undefined : "waiting"}
        />
      </div>

      {stale && latest ? (
        <p
          className="shrink-0 rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive"
          role="status"
        >
          No run since {fullDate(latest.created_at)}. The schedule may have
          stopped - check the Auto-drafts workflow on GitHub.
        </p>
      ) : null}

      <section className="shrink-0 space-y-2">
        <h2 className="text-sm font-medium text-muted-foreground">Pages</h2>
        <div className="overflow-hidden rounded-xl border">
          <table className="w-full text-sm">
            <thead className="border-b bg-muted/40 text-xs text-muted-foreground">
              <tr>
                <th className="px-3 py-2 text-left font-medium">Page</th>
                <th className="px-3 py-2 text-right font-medium">Posts left</th>
                <th className="px-3 py-2 text-left font-medium">Last run</th>
              </tr>
            </thead>
            <tbody>
              {data.pages.map((page) => {
                const state = pool(page);
                return (
                  <tr key={page.page_id} className="border-b last:border-0 align-top">
                    <td className="px-3 py-2.5">
                      <div className="font-medium">{page.page_name}</div>
                      {state.detail ? (
                        <div className="mt-0.5 text-xs text-muted-foreground">
                          {state.detail}
                        </div>
                      ) : null}
                    </td>
                    <td
                      className={cn(
                        "px-3 py-2.5 text-right tabular-nums",
                        page.available === 0 && page.assigned_competitors > 0
                          ? "text-destructive"
                          : null,
                      )}
                    >
                      <div className="flex items-center justify-end gap-2">
                        {page.available}
                        <StatusPill tone={state.tone} label={state.label} />
                      </div>
                    </td>
                    <td className="px-3 py-2.5 text-muted-foreground">
                      {page.last_run_at ? (
                        <>
                          <div>
                            {page.last_run_drafts} draft
                            {page.last_run_drafts === 1 ? "" : "s"},{" "}
                            {timeAgo(page.last_run_at)}
                          </div>
                          {page.last_run_note ? (
                            <div className="mt-0.5 text-xs">{page.last_run_note}</div>
                          ) : null}
                        </>
                      ) : (
                        <span className="text-xs">Not automated</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      <section className="shrink-0 space-y-2">
        <h2 className="text-sm font-medium text-muted-foreground">Recent runs</h2>
        {data.runs.length === 0 ? (
          <p className="rounded-xl border px-3 py-6 text-center text-sm text-muted-foreground">
            Nothing has run yet. The schedule writes its first row at 18:00.
          </p>
        ) : (
          <ul className="overflow-hidden rounded-xl border text-sm">
            {data.runs.map((run) => {
              const page = data.pages.find((row) => row.page_id === run.page_id);
              return (
                <li
                  key={run.id}
                  className="flex items-baseline justify-between gap-4 border-b px-3 py-2 last:border-0"
                >
                  <span className="min-w-0">
                    <span className="font-medium">{page?.page_name ?? `Page ${run.page_id}`}</span>
                    {run.note ? (
                      <span className="ml-2 text-xs text-muted-foreground">{run.note}</span>
                    ) : null}
                  </span>
                  <span className="shrink-0 tabular-nums text-muted-foreground">
                    {run.drafts_created} draft{run.drafts_created === 1 ? "" : "s"}
                    <span className="ml-3 text-xs">{timeAgo(run.created_at)}</span>
                  </span>
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </div>
  );
}

/**
 * Now, to the minute, or null before hydration.
 *
 * A clock read during render is a hydration mismatch, and reading it in an
 * effect is a cascading render - `useSyncExternalStore` is the shape React
 * provides for exactly this: the server snapshot is null, so the first paint
 * agrees with the server, and the client subscribes to a ticking store.
 *
 * The snapshot is the minute index rather than a `Date`, because
 * `getSnapshot` must return a value that does not change between renders
 * within the same tick. A fresh `Date` fails that and re-renders forever.
 */
function useMinuteClock(): Date | null {
  const minute = useSyncExternalStore(
    (onChange) => {
      const timer = setInterval(onChange, 60_000);
      return () => clearInterval(timer);
    },
    () => Math.floor(Date.now() / 60_000),
    () => null,
  );
  return minute === null ? null : new Date(minute * 60_000);
}


/** One headline number. The three questions the screen exists to answer. */
function Tile({
  label,
  value,
  detail,
  tone,
}: {
  label: string;
  value: string;
  detail?: string;
  tone?: "negative" | "waiting";
}) {
  return (
    <div
      className={cn(
        "rounded-xl border px-4 py-3",
        tone === "negative" && "border-destructive/30 bg-destructive/5",
        tone === "waiting" && "border-amber-500/30 bg-amber-500/5",
      )}
    >
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="mt-1 text-lg font-semibold tracking-tight">{value}</div>
      {detail ? (
        <div className="mt-0.5 truncate text-xs text-muted-foreground" title={detail}>
          {detail}
        </div>
      ) : null}
    </div>
  );
}
