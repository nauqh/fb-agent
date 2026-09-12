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
 * chart: **reach** and **engagement**.
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
  days,
  /** The window's start, fixed when the read was made. */
  cutoff,
}: {
  /** The current window, best first. */
  posts: PostStats[];
  days: number;
  cutoff: number;
}) {
  const { series, maxReach, reachTicks } = useMemo(() => {
    // One bucket per Page-zone day (the same zone every other screen groups
    // by). The zone has no DST, so a 24h walk from the window's first day
    // lands on one entry per calendar day.
    const xMax = cutoff + days * 86_400_000;
    const buckets = new Map<string, DayPoint>();
    for (let t = cutoff; t < xMax; t += 86_400_000) {
      const key = DAY_KEY.format(t);
      buckets.set(key, { t, key, engagement: 0, reach: 0, count: 0 });
    }
    for (const post of posts) {
      if (post.published_at === null) continue;
      const bucket = buckets.get(DAY_KEY.format(asUtc(post.published_at).getTime()));
      if (!bucket) continue;
      bucket.engagement += post.engagement;
      bucket.reach += post.impressions;
      bucket.count += 1;
    }

    const series = [...buckets.values()].sort((a, b) => a.t - b.t);

    // `Math.max(1, ...)` guards an all-zero window - a young Page whose posts
    // have no counts yet would otherwise hand the scale a 0 domain.
    const maxReach = Math.max(1, ...series.map((day) => day.reach));

    // Round figures at positions the eye can compare.
    const LADDER = [
      0, 100, 250, 500, 1_000, 2_500, 5_000, 10_000, 25_000, 50_000, 100_000,
      250_000, 500_000, 1_000_000, 2_500_000, 5_000_000, 10_000_000,
    ];
    const reachTicks = [0, ...LADDER.filter((v) => 0 < v && v <= maxReach).slice(-5)];

    return { series, maxReach, reachTicks };
  }, [posts, days, cutoff]);

  return (
    <figure className="m-0 mt-2 pb-4">
      {/* A named chart, not an anonymous block: the one sentence the frame
          answers, in the same furniture type the table's column labels use.
          The window pill beside the tabs already says "last 30 days". */}
      <div className="px-0.5 pb-1 font-mono text-[10px] tracking-[0.12em] text-muted-foreground uppercase">
        Reach and engagement, daily
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
        className="font-mono"
      >
        <ResponsiveContainer width="100%" height={320}>
          <LineChart
            data={series}
            margin={{ top: 8, right: 4, bottom: 0, left: 0 }}
          >
            <defs>
              {/* The fill under the reach line, fading to nothing so the
                  engagement line beneath it is never sitting on grey. */}
              <linearGradient id="reach-fill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#3b82f6" stopOpacity={0.16} />
                <stop offset="100%" stopColor="#3b82f6" stopOpacity={0} />
              </linearGradient>
            </defs>

            {/* Hairline rules at the left axis's ticks. Border grey is
                near-invisible on the card at any opacity, so this is the
                tick colour itself, well faded. */}
            {/* Hairline rules at the left axis's ticks - all but the topmost,
                which would read as a frame's top border where there is no
                frame. Drawn by hand rather than CartesianGrid for exactly
                that control, at the tick colour well faded. */}
            {reachTicks.slice(0, -1).map((tick) => (
              <ReferenceLine
                key={tick}
                yAxisId="reach"
                y={tick}
                stroke="var(--muted-foreground)"
                strokeOpacity={0.15}
              />
            ))}

            <XAxis
              dataKey="t"
              type="number"
              scale="time"
              domain={["dataMin", "dataMax"]}
              tickFormatter={(t: number) => DAY_MONTH.format(t)}
              tick={{ fontSize: 10, fill: "var(--muted-foreground)" }}
              axisLine={{ stroke: "var(--border)" }}
              tickLine={false}
              tickMargin={6}
              minTickGap={56}
            />
            <YAxis
              yAxisId="reach"
              dataKey="reach"
              type="number"
              domain={[0, maxReach * 1.05]}
              ticks={reachTicks}
              tickFormatter={metric}
              tick={{ fontSize: 10, fill: "var(--muted-foreground)" }}
              axisLine={false}
              tickLine={false}
              width={40}
            />
            <YAxis
              yAxisId="eng"
              orientation="right"
              dataKey="engagement"
              type="number"
              domain={[0, (yMax) => yMax * 1.1]}
              tickFormatter={metric}
              allowDecimals={false}
              tick={{ fontSize: 10, fill: "var(--muted-foreground)" }}
              axisLine={false}
              tickLine={false}
              width={36}
            />

            {/* Reach: the wider story, carrying the fill. Blue, so the two
                lines separate at a glance instead of by darkness - hex
                rather than a theme token, because the app's greys are the
                *absence* of a choice and two lines need two choices. */}
            <Line
              yAxisId="reach"
              dataKey="reach"
              stroke="#3b82f6"
              strokeWidth={1.5}
              fill="url(#reach-fill)"
              type="monotone"
              dot={false}
              activeDot={{ r: 3, strokeWidth: 0 }}
            />
            {/* Engagement: the metric the list is sorted by, on its own
                scale at the right edge. Amber, kin to the app's gold accent
                but dark enough to hold its own on the light theme. */}
            <Line
              yAxisId="eng"
              dataKey="engagement"
              stroke="#f59e0b"
              strokeWidth={1.5}
              type="monotone"
              dot={false}
              activeDot={{ r: 3, strokeWidth: 0 }}
            />

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
      </figcaption>
    </figure>
  );
}

/**
 * Hover card for one day: what went out, what it did.
 *
 * The three totals a day's row of the table would add up to. The post count
 * is what turns a dip into an answer - "quiet because nothing was published"
 * reads differently from "published and ignored".
 */
function DayTip({ day }: { day: DayPoint }) {
  return (
    <div className="min-w-44 rounded-lg border bg-popover/95 px-3 py-2.5 shadow-md backdrop-blur-sm">
      <p className="text-[11px] text-muted-foreground">
        {DAY_TIP.format(day.t)}
      </p>
      <div className="mt-1.5 flex flex-wrap items-baseline gap-x-3 gap-y-0.5 font-mono text-[11px]">
        <span className="font-semibold text-[#3b82f6]">
          {metric(day.reach)} reach
        </span>
        <span className="text-[#f59e0b]">{metric(day.engagement)} eng</span>
        <span className="text-muted-foreground">
          {day.count} post{day.count === 1 ? "" : "s"}
        </span>
      </div>
    </div>
  );
}

interface DayPoint {
  /** Bucket start, epoch ms - the x coordinate. */
  t: number;
  /** `2026-09-12` in the Page's zone - the bucket key. */
  key: string;
  engagement: number;
  reach: number;
  count: number;
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
