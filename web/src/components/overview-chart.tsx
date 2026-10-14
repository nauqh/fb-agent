"use client";

import { useMemo } from "react";
import {
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { PostStats } from "@/lib/api/overview";
import { PAGE_TIMEZONE, asUtc, metric } from "@/lib/format";

/**
 * The window's two headline statistics, day by day, as a plain multiline
 * chart: **reach** and **engagement**, each a 7-day rolling average.
 *
 * Posts are bucketed by publish day with their lifetime counts, so a raw daily
 * line was one viral post or none: House of Common Sense went 2.88M, 41K, 482
 * over 12-14 Oct 2026. The average shows the trend under that. The last two
 * days are dashed: their posts are hours old and still counting.
 *
 * Reach always rides above engagement (impressions are counted in the
 * thousands, reactions in the hundreds), so the two lines never cross and a
 * shared x axis carries both without either needing to touch the other's
 * scale - each gets its own y axis instead, left for reach, right for
 * engagement.
 *
 * One line per statistic, current window only. The previous window is in the
 * summary line's delta chip; overlaying four lines here to repeat that one
 * percentage is how a chart stops being read.
 */
export function PerformanceChart({
  posts,
  previous,
  days,
  /** The window's start, fixed when the read was made. */
  cutoff,
}: {
  /** The current window, best first. */
  posts: PostStats[];
  /** The window before, for the first days' trailing average. */
  previous: PostStats[];
  days: number;
  cutoff: number;
}) {
  const { series, reachTicks, top, xTicks } = useMemo(() => {
    // One bucket per Page-zone day (the same zone every other screen groups
    // by). The zone has no DST, so a 24h walk from the window's first day
    // lands on one entry per calendar day.
    const xMax = cutoff + days * 86_400_000;
    const buckets = new Map<string, DayPoint>();
    for (let t = cutoff - (AVERAGE_DAYS - 1) * 86_400_000; t < xMax; t += 86_400_000) {
      const key = DAY_KEY.format(t);
      buckets.set(key, {
        t, key, engagement: 0, reach: 0, count: 0, reachAvg: 0, engagementAvg: 0, fresh: false,
      });
    }
    for (const post of [...posts, ...previous]) {
      if (post.published_at === null) continue;
      const bucket = buckets.get(DAY_KEY.format(asUtc(post.published_at).getTime()));
      if (!bucket) continue;
      bucket.engagement += post.engagement;
      bucket.reach += post.impressions;
      bucket.count += 1;
    }

    // A day with no posts counts as zero: nothing went out to be seen. Days
    // before the Page's first post are not days at all - averaged in as zeros,
    // a Page started mid-window (House of Common Sense, 15 Sept 2026) drew a
    // week-long climb from nothing that was only the average filling up.
    const all = [...buckets.values()].sort((a, b) => a.t - b.t);
    const first = Math.max(0, all.findIndex((day) => day.count > 0));
    const freshFrom = xMax - FRESH_DAYS * 86_400_000;
    all.forEach((day, i) => {
      const week = all.slice(Math.max(first, i - AVERAGE_DAYS + 1), i + 1);
      day.reachAvg = week.reduce((sum, d) => sum + d.reach, 0) / week.length;
      day.engagementAvg = week.reduce((sum, d) => sum + d.engagement, 0) / week.length;
      day.fresh = day.t >= freshFrom;
      day.joins = day.t < freshFrom && day.t + 86_400_000 >= freshFrom;
    });
    const series = all.filter((day, i) => day.t >= cutoff && i >= first);

    // `Math.max(1, ...)` guards an all-zero window - a young Page whose posts
    // have no counts yet would otherwise hand the scale a 0 domain.
    const maxReach = Math.max(1, ...series.map((day) => day.reachAvg));
    // Even rules, not a ladder. Round ladder values (10K, 25K, 50K, 100K)
    // cannot be evenly spaced on a linear axis - the lines bunched at the
    // bottom and stretched at the top. One step instead, sized to give
    // about five divisions, so every rule sits the same distance from its
    // neighbours and every label is still a round number.
    const raw = maxReach / 5;
    const pow = 10 ** Math.floor(Math.log10(raw));
    const step =
      [1, 2, 5, 10].map((m) => m * pow).find((m) => m >= raw) ?? 10 * pow;
    const top = step * Math.ceil(maxReach / step);
    const reachTicks = Array.from(
      { length: Math.ceil(maxReach / step) + 1 },
      (_, i) => i * step,
    );

    // Vertical rules, at whole-day steps that divide the window exactly and
    // leave about a dozen columns - graph-paper density rather than four
    // wide panes. The date labels ride the same ticks; twelve short mono
    // stamps fit the plot's width, and every label still lands on a rule.
    const spanDays = days * 2;
    const STEP_CANDIDATES = [1, 2, 3, 5, 7, 10, 14, 15, 20, 30];
    const stepDays =
      STEP_CANDIDATES.find(
        (s) => spanDays % s === 0 && spanDays / s >= 8 && spanDays / s <= 15,
      ) ?? Math.round(spanDays / 12);
    const xTicks: number[] = [];
    for (let t = cutoff; t <= xMax; t += stepDays * 86_400_000) {
      xTicks.push(t);
    }

    return { series, maxReach, reachTicks, top, xTicks };
  }, [posts, previous, days, cutoff]);

  return (
    <figure className="m-0 mt-2 pb-4">
      {/* A named chart, not an anonymous block: the one sentence the frame
          answers. Larger than the axis furniture beneath it, since it is
          what a scanning eye lands on first. */}
      <div className="px-0.5 pb-1.5 text-base font-semibold tracking-tight text-foreground">
        Reach and engagement, 7-day average
      </div>
      {/* Axis names, once, at the top of their scales - the ticks are mono
          digits, the words are what they count. Set in the foreground, one
          step bolder than the ticks beneath them, and aligned to their own
          gutters. The x axis names itself: dates. */}
      <div className="flex items-center justify-between px-1 pb-1.5 text-[11px] font-medium">
        <span className="text-foreground">Reach</span>
        <span className="text-foreground">Engagement</span>
      </div>
      <div
        role="img"
        aria-label={`Reach and engagement per day over the last ${days} days.`}
      >
        <ResponsiveContainer width="100%" height={320}>
          <LineChart
            data={series}
            margin={{ top: 8, right: 4, bottom: 0, left: 0 }}
          >
            {/* Dim rules in both directions. Hand-drawn ReferenceLines rather
                than CartesianGrid: the grid's horizontal lines come from the
                default-id y axis, and both of ours are named, so the library
                draws the verticals and quietly skips the horizontals.
                Topmost horizontal and the edge verticals stay off - at the
                frame's edges they read as a border where there is no frame. */}
            {/* Rules at the ticks, both ways. Horizontal: every reach tick
                including the topmost - with even spacing, the topmost is a
                gridline like the rest, sitting just under the domain's
                slack. Vertical: inset from both edges, where a rule would
                read as a frame's border; the edge dates keep their labels. */}
            {reachTicks.map((tick) => (
              <ReferenceLine
                key={`h-${tick}`}
                yAxisId="reach"
                y={tick}
                stroke="var(--muted-foreground)"
                strokeOpacity={0.12}
              />
            ))}
            {xTicks.map((t) => (
              <ReferenceLine
                key={`v-${t}`}
                yAxisId="reach"
                x={t}
                stroke="var(--muted-foreground)"
                strokeOpacity={0.12}
              />
            ))}

            <XAxis
              dataKey="t"
              type="number"
              scale="time"
              domain={[cutoff, cutoff + days * 86_400_000]}
              ticks={xTicks}
              tickFormatter={(t: number) => DAY_MONTH.format(t)}
              tick={{ fontSize: 10, fill: "var(--muted-foreground)" }}
              axisLine={{ stroke: "var(--foreground)" }}
              tickLine={false}
              tickMargin={6}
            />
            <YAxis
              yAxisId="reach"
              dataKey="reachAvg"
              type="number"
              domain={[0, top * 1.05]}
              ticks={reachTicks}
              tickFormatter={metric}
              tick={{ fontSize: 10, fill: "var(--muted-foreground)" }}
              axisLine={{ stroke: "var(--foreground)" }}
              tickLine={false}
              width={40}
            />
            <YAxis
              yAxisId="eng"
              orientation="right"
              dataKey="engagementAvg"
              type="number"
              domain={[0, (yMax) => yMax * 1.1]}
              tickFormatter={metric}
              allowDecimals={false}
              tick={{ fontSize: 10, fill: "var(--muted-foreground)" }}
              axisLine={{ stroke: "var(--foreground)" }}
              tickLine={false}
              width={36}
            />

            {/* Reach: the wider story. Blue, so the two lines separate at a
                glance instead of by darkness - hex rather than a theme token,
                because the app's greys are the *absence* of a choice and two
                lines need two choices. Engagement: the metric the list is
                sorted by, on its own scale at the right edge. Amber, kin to
                the app's gold accent. Each is drawn twice, solid to the last
                settled day and dashed from there, sharing the joining point. */}
            {(["reach", "eng"] as const).flatMap((axis) =>
              [false, true].map((dashed) => (
                <Line
                  key={`${axis}-${dashed}`}
                  yAxisId={axis}
                  dataKey={plotted(axis === "reach" ? "reachAvg" : "engagementAvg", dashed)}
                  stroke={axis === "reach" ? "#3b82f6" : "#f59e0b"}
                  strokeWidth={1.5}
                  strokeDasharray={dashed ? "4 3" : undefined}
                  type="monotone"
                  dot={false}
                  activeDot={dashed ? false : { r: 3, strokeWidth: 0 }}
                  isAnimationActive={false}
                />
              )),
            )}

            <Tooltip
              cursor={{ stroke: "var(--border)", strokeDasharray: "3 3" }}
              content={({ active, payload }) => {
                if (!active || !payload?.length) return null;
                const day = payload[0].payload as DayPoint;
                return <DayTip day={day} />;
              }}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* The key, as a caption rather than a recharts Legend: two plain
          phrases, one muted line, no box. */}
      <figcaption className="flex flex-wrap items-center gap-x-4 gap-y-1 px-0.5 pt-1 text-[11px] text-muted-foreground">
        <span className="inline-flex items-center gap-1.5">
          <span aria-hidden className="h-1.5 w-4 rounded-full bg-[#3b82f6]" />
          reach / day
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span aria-hidden className="h-1.5 w-4 rounded-full bg-[#f59e0b]" />
          engagement / day
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span aria-hidden className="w-4 border-t border-dashed border-muted-foreground" />
          still counting
        </span>
      </figcaption>
    </figure>
  );
}

/**
 * Hover card for one day: the averages plotted, then what went out that day.
 *
 * The post count is what turns a dip into an answer - "quiet because nothing
 * was published" reads differently from "published and ignored".
 */
function DayTip({ day }: { day: DayPoint }) {
  return (
    <div className="min-w-44 rounded-lg border bg-popover/95 px-3 py-2.5 shadow-md backdrop-blur-sm">
      <p className="text-[11px] text-muted-foreground">
        {DAY_TIP.format(day.t)}
        {day.fresh ? " · still counting" : ""}
      </p>
      <div className="mt-1.5 flex flex-wrap items-baseline gap-x-3 gap-y-0.5 text-xs">
        <span className="font-semibold text-[#3b82f6]">
          {metric(Math.round(day.reachAvg))} reach
        </span>
        <span className="text-[#f59e0b]">
          {metric(Math.round(day.engagementAvg))} eng
        </span>
        <span className="text-muted-foreground">7-day avg</span>
      </div>
      <p className="mt-1 text-[11px] text-muted-foreground">
        That day: {day.count} post{day.count === 1 ? "" : "s"}, {metric(day.reach)} reach
      </p>
    </div>
  );
}

/**
 * The solid line stops at the last settled day; the dashed one starts there,
 * so the two meet on one point instead of leaving a gap.
 */
function plotted(key: "reachAvg" | "engagementAvg", dashed: boolean) {
  return (day: DayPoint) =>
    (dashed ? day.fresh || day.joins : !day.fresh) ? day[key] : null;
}

const AVERAGE_DAYS = 7;
const FRESH_DAYS = 2;

interface DayPoint {
  /** Bucket start, epoch ms - the x coordinate. */
  t: number;
  /** `2026-09-12` in the Page's zone - the bucket key. */
  key: string;
  engagement: number;
  reach: number;
  count: number;
  reachAvg: number;
  engagementAvg: number;
  /** In the last `FRESH_DAYS`, whose posts are still gathering counts. */
  fresh: boolean;
  /** The last settled day, where the dashed line picks up. */
  joins?: boolean;
}

/** Bucket keys, `2026-09-12` style - the same shape `dayKey()` gives rows. */
const DAY_KEY = new Intl.DateTimeFormat("en-CA", {
  timeZone: PAGE_TIMEZONE,
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
});

const DAY_MONTH = new Intl.DateTimeFormat("en-GB", {
  timeZone: PAGE_TIMEZONE,
  day: "numeric",
  month: "short",
});

const DAY_TIP = new Intl.DateTimeFormat("en-GB", {
  timeZone: PAGE_TIMEZONE,
  weekday: "short",
  day: "numeric",
  month: "short",
});
