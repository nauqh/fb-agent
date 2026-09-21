"use client";

import { useSyncExternalStore } from "react";
import { AlertTriangle } from "lucide-react";

import { Loading } from "@/components/loading";
import { PageBadge } from "@/components/page-badge";
import { QueryError } from "@/components/query-error";
import { ScreenHeader } from "@/components/screen";
import { StatusPill, type StatusTone } from "@/components/status-pill";
import { getAutoDraftStatus } from "@/lib/api/auto-drafts";
import { asUtc, dayHeading, timeAgo, timeOfDay } from "@/lib/format";
import { pageAvatarRaw } from "@/lib/page-avatar";
import type { AutoDraftPage, AutoDraftRun, AutoDraftStatus } from "@/lib/types";
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
 * The shape is the Overview's, not a dashboard's. This began as three boxed
 * tiles over a bordered table and read as a control panel: three equal boxes
 * make nothing important, which is the opposite of what a monitor is for. The
 * summary is one line now - figures carrying the weight, words between them
 * muted - and both tables are the app's own, down to the mono uppercase header
 * and the day headings the Review queue groups by.
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

const BATCH_MINUTES = 10;
/**
 * How far back "the last run" reaches when totalling its drafts.
 *
 * One run writes a row per Page microseconds apart, so an equal-timestamp test
 * matched a single row and reported one Page's drafts as the whole night's.
 * Ten minutes is far longer than a run takes to record and far shorter than a
 * day between runs.
 */

const LOW_WATER = 5;
/** At or below this many unused posts, a Page is worth looking at. */

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
 * response. The sentence is a tooltip rather than a line under the name -
 * seven rows of explanation competed with the data they were explaining.
 */
function pool(page: AutoDraftPage): { tone: StatusTone; label: string; why: string } {
  if (page.last_run_at === null) {
    return {
      tone: "neutral",
      label: "Not automated",
      why:
        page.assigned_competitors === 0
          ? "Not in the schedule, and no competitors are ticked for it."
          : `Not in the schedule. It has ${page.available} unused posts if you add it.`,
    };
  }
  if (page.assigned_competitors === 0) {
    return {
      tone: "neutral",
      label: "Not set up",
      why: "No competitors are ticked for this Page. Add some on Settings before automating it.",
    };
  }
  if (page.available === 0) {
    return {
      tone: "negative",
      label: "Nothing left",
      why: "Every competitor post in the last 7 days has been written about already.",
    };
  }
  if (page.available <= LOW_WATER) {
    return {
      tone: "waiting",
      label: "Running low",
      why: `${page.available} unused posts left in the last 7 days.`,
    };
  }
  return {
    tone: "positive",
    label: "Ready",
    why: `${page.available} unused posts left in the last 7 days.`,
  };
}

export default function AutoDraftsScreen() {
  const { data, error } = useQuery<AutoDraftStatus>(
    () => getAutoDraftStatus(30),
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
  const stale =
    now !== null &&
    latest !== null &&
    (now.getTime() - asUtc(latest.created_at).getTime()) / 3_600_000 > STALE_AFTER_HOURS;

  const lastDrafts = latest
    ? data.runs
        .filter(
          (run) =>
            asUtc(latest.created_at).getTime() - asUtc(run.created_at).getTime() <
            BATCH_MINUTES * 60_000,
        )
        .reduce((sum, run) => sum + run.drafts_created, 0)
    : 0;

  const automated = data.pages.filter((page) => page.last_run_at !== null);
  const attention = automated.filter((page) => page.available <= LOW_WATER);
  // The bar is relative to the healthiest Page, the way the Overview scales
  // engagement against its best row. An absolute scale would need a ceiling
  // nobody could defend.
  const best = Math.max(1, ...data.pages.map((page) => page.available));

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-5 overflow-y-auto pb-10">
      <ScreenHeader
        title="Auto-drafts"
        hint="Writes drafts into Review once a day. Every Page, not just the selected one."
        // Off: this screen is about all Pages at once, so a Page name in the
        // title row would claim a scope it does not have. Same reasoning as
        // Global.
        switcher={false}
      />

      {/* The Overview's summary line, and for its reasons: the figures carry
          the weight, the words between them stay muted, and it costs one line
          where three boxes cost a band across the screen. */}
      <p className="flex flex-wrap items-center gap-x-2 gap-y-1 px-0.5 text-sm text-muted-foreground">
        <Figure value={now ? until(nextRun(now), now) : "-"} label="until the next run" />
        <span aria-hidden>·</span>
        <Figure value={String(automated.length)} label="Pages automated" />
        {latest ? (
          <>
            <span aria-hidden>·</span>
            <Figure
              value={String(lastDrafts)}
              label={`drafts ${timeAgo(latest.created_at)}`}
            />
          </>
        ) : null}

        {attention.length > 0 ? (
          <span
            title={attention.map((page) => page.page_name).join(", ")}
            className="inline-flex items-center gap-1 rounded-full bg-gold/15 px-2 py-0.5 text-xs font-medium tabular-nums text-foreground"
          >
            <AlertTriangle className="size-3" />
            {attention.length}
            <span className="font-normal text-muted-foreground">
              {attention.length === 1 ? "Page needs attention" : "Pages need attention"}
            </span>
          </span>
        ) : null}
      </p>

      {stale && latest ? (
        <p
          role="status"
          className="flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive"
        >
          <AlertTriangle className="mt-0.5 size-4 shrink-0" />
          <span>
            Nothing has run since {timeAgo(latest.created_at)}. The schedule may
            have stopped - check the Auto-drafts workflow on GitHub.
          </span>
        </p>
      ) : null}

      <section className="shrink-0 overflow-hidden rounded-xl border">
        <table className="w-full">
          <thead>
            <tr className="border-b bg-muted/30 text-left font-mono text-[11px] uppercase tracking-[0.12em] text-muted-foreground">
              <th className="px-5 py-3 font-medium">Page</th>
              <th className="w-52 px-5 py-3 font-medium">Posts left</th>
              <th className="w-44 px-5 py-3 font-medium">Last run</th>
              <th className="w-40 px-5 py-3 font-medium">Status</th>
            </tr>
          </thead>
          <tbody>
            {data.pages.map((page) => {
              const state = pool(page);
              return (
                <tr
                  key={page.page_id}
                  className={cn(
                    "border-b transition-colors last:border-0 hover:bg-muted/30",
                    page.last_run_at === null && "opacity-60",
                  )}
                >
                  <td className="px-5 py-3">
                    <PageBadge
                      name={page.page_name}
                      avatarPath={pageAvatarRaw(page)}
                      className="text-[13px]"
                    />
                  </td>

                  <td className="px-5 py-3" title={state.why}>
                    <div className="flex items-center gap-2.5">
                      <span
                        className={cn(
                          "w-8 shrink-0 text-right text-[13px] font-medium tabular-nums",
                          page.available === 0 && page.assigned_competitors > 0
                            ? "text-destructive"
                            : null,
                        )}
                      >
                        {page.available}
                      </span>
                      <Bar share={page.available / best} tone={state.tone} />
                    </div>
                  </td>

                  <td className="whitespace-nowrap px-5 py-3 text-[13px] text-muted-foreground">
                    {page.last_run_at ? (
                      <>
                        <span className="tabular-nums">{page.last_run_drafts}</span>{" "}
                        {page.last_run_drafts === 1 ? "draft" : "drafts"},{" "}
                        {timeAgo(page.last_run_at)}
                      </>
                    ) : (
                      <span className="text-muted-foreground/70">Not automated</span>
                    )}
                  </td>

                  <td className="px-5 py-3">
                    {page.last_run_at === null ? (
                      <span className="text-[13px] text-muted-foreground/60">-</span>
                    ) : (
                      <StatusPill tone={state.tone} label={state.label} />
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </section>

      <RunLog runs={data.runs} pages={data.pages} />
    </div>
  );
}

/**
 * The log, grouped by day.
 *
 * Grouped rather than listed because ungrouped it repeated the table above it -
 * the same Page names and the same counts, twice on one screen. A day heading
 * turns it into what it actually is: a history, where the useful reading is
 * "every night this week ran" rather than any single row.
 */
function RunLog({ runs, pages }: { runs: AutoDraftRun[]; pages: AutoDraftPage[] }) {
  if (runs.length === 0) {
    return (
      <section className="shrink-0 rounded-xl border px-5 py-8 text-center text-sm text-muted-foreground">
        Nothing has run yet. The first run writes its rows at 18:00.
      </section>
    );
  }

  const named = (id: number) => pages.find((page) => page.page_id === id) ?? null;

  const days: { heading: string; rows: AutoDraftRun[] }[] = [];
  for (const run of runs) {
    const heading = dayHeading(run.created_at);
    const current = days.at(-1);
    if (current && current.heading === heading) current.rows.push(run);
    else days.push({ heading, rows: [run] });
  }

  return (
    <section className="shrink-0 space-y-2">
      <h2 className="px-0.5 text-sm font-medium text-muted-foreground">Run history</h2>
      <div className="overflow-hidden rounded-xl border">
      <table className="w-full">
        <thead>
          <tr className="border-b bg-muted/30 text-left font-mono text-[11px] uppercase tracking-[0.12em] text-muted-foreground">
            <th className="px-5 py-3 font-medium">Page</th>
            <th className="w-56 px-5 py-3 font-medium">Result</th>
            <th className="w-24 px-5 py-3 text-right font-medium">Time</th>
          </tr>
        </thead>
        <tbody>
          {days.map((day) => (
            <Day key={day.heading} heading={day.heading} rows={day.rows} named={named} />
          ))}
        </tbody>
      </table>
      </div>
    </section>
  );
}

function Day({
  heading,
  rows,
  named,
}: {
  heading: string;
  rows: AutoDraftRun[];
  named: (id: number) => AutoDraftPage | null;
}) {
  const total = rows.reduce((sum, run) => sum + run.drafts_created, 0);

  return (
    <>
      {/* The Review queue's day heading, verbatim in style: the count beside it
          is what makes the group worth having. */}
      <tr className="border-b bg-muted/20">
        <td
          colSpan={3}
          className="px-5 py-1.5 font-mono text-[11px] font-medium uppercase tracking-[0.12em] text-muted-foreground"
        >
          {heading}{" "}
          <span className="text-muted-foreground/60">
            {total} {total === 1 ? "draft" : "drafts"}
          </span>
        </td>
      </tr>

      {rows.map((run) => {
        const page = named(run.page_id);
        return (
          <tr
            key={run.id}
            className="border-b transition-colors last:border-0 hover:bg-muted/30"
          >
            <td className="px-5 py-2.5 text-[13px] font-medium">
              {page?.page_name ?? `Page ${run.page_id}`}
            </td>

            <td className="px-5 py-2.5 text-[13px]">
              {run.drafts_created > 0 ? (
                <span className="tabular-nums">
                  {run.drafts_created} {run.drafts_created === 1 ? "draft" : "drafts"}
                </span>
              ) : (
                <span className="text-muted-foreground">Nothing to write about</span>
              )}
            </td>

            <td className="whitespace-nowrap px-5 py-2.5 text-right text-[13px] tabular-nums text-muted-foreground">
              {timeOfDay(run.created_at)}
            </td>
          </tr>
        );
      })}
    </>
  );
}

/** One figure of the summary line: the number carries the weight, the word does not. */
function Figure({ value, label }: { value: string; label: string }) {
  return (
    <span>
      <span className="font-semibold tabular-nums text-foreground">{value}</span> {label}
    </span>
  );
}

/**
 * How much material a Page has left, drawn.
 *
 * A number alone makes the reader compare seven figures; a bar makes the short
 * one obvious without reading any of them. Tinted by the same state the pill
 * carries, so colour is stated twice on the row rather than inventing a third
 * scale.
 */
function Bar({ share, tone }: { share: number; tone: StatusTone }) {
  const fill =
    tone === "negative"
      ? "bg-destructive"
      : tone === "waiting"
        ? "bg-gold"
        : tone === "neutral"
          ? "bg-muted-foreground/30"
          : "bg-foreground/35";

  return (
    <span className="h-1.5 min-w-0 flex-1 overflow-hidden rounded-full bg-foreground/[0.07]">
      <span
        className={cn("block h-full origin-left rounded-full transition-transform", fill)}
        style={{ transform: `scaleX(${Math.max(0, Math.min(1, share))})` }}
      />
    </span>
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
 * The snapshot is the minute index rather than a `Date`, because `getSnapshot`
 * must return a value that does not change between renders within the same
 * tick. A fresh `Date` fails that and re-renders forever.
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
