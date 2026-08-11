"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";

import { Button } from "@/components/ui/button";
import { pageNoon, pageToday } from "@/lib/format";
import type { ScheduledPost } from "@/lib/types";
import { cn } from "@/lib/utils";

/**
 * The week, as a grid of the slots actually in use.
 *
 * **Rows are derived from the data, not from the clock.** The obvious grid is 24
 * hour-rows, which is what a general calendar needs; this page is not general.
 * Measured across a fortnight of History Retraced: 9-10 posts a day at ten
 * distinct hours — roughly every two hours from midnight to noon, then 20:00 and
 * 22:00. Twenty-four rows would be half empty and twice as tall, and the reader
 * would scroll past fourteen blank bands to compare Tuesday with Wednesday.
 *
 * That regularity is also the argument for a grid at all. When slots repeat, the
 * useful question is *which slot is empty* — and an absence cannot be rendered
 * in a list. A missing 08:00 is invisible in a feed of what exists and obvious
 * as a hole in a column.
 */
export function ScheduleWeek({
  posts,
  weekStart,
  onWeekChange,
}: {
  posts: ScheduledPost[];
  weekStart: Date;
  onWeekChange: (next: Date) => void;
}) {
  const days = weekDays(weekStart);
  const inWeek = posts.filter((post) => days.includes(post.published_at.slice(0, 10)));
  const slots = slotRows(inWeek);

  const byCell = new Map<string, ScheduledPost[]>();
  for (const post of inWeek) {
    const key = `${post.published_at.slice(0, 10)}|${nearestSlot(post, slots)}`;
    const cell = byCell.get(key);
    if (cell) cell.push(post);
    else byCell.set(key, [post]);
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3">
      <div className="flex shrink-0 items-center gap-2">
        <Button variant="outline" size="icon-sm" onClick={() => onWeekChange(shift(weekStart, -7))}>
          <ChevronLeft className="size-4" />
        </Button>
        <Button variant="outline" size="icon-sm" onClick={() => onWeekChange(shift(weekStart, 7))}>
          <ChevronRight className="size-4" />
        </Button>
        <Button variant="ghost" size="sm" onClick={() => onWeekChange(startOfWeek(pageNoon()))}>
          This week
        </Button>
        <p className="ml-2 text-sm text-muted-foreground">
          {label(days[0])} — {label(days[6])}
          <span className="ml-2 tabular-nums">· {inWeek.length} posts</span>
        </p>
      </div>

      {/* Vertical is `hidden`, not `auto`: the rows divide the height that is
          left, so there is never anything below the fold. Horizontal stays
          scrollable because seven columns have a floor a narrow window cannot
          honour, and squeezing them further makes the chips unreadable. */}
      <div className="flex min-h-0 flex-1 flex-col overflow-x-auto overflow-y-hidden rounded-xl border">
        <div className="flex min-h-0 min-w-[860px] flex-1 flex-col">
          {/* Day headers */}
          <div className="grid shrink-0 grid-cols-[4rem_repeat(7,minmax(0,1fr))] border-b bg-muted/30">
            <div />
            {days.map((day) => (
              <div
                key={day}
                className={cn(
                  "px-2 py-2 text-center text-[11px] font-medium",
                  day === todayKey() ? "text-foreground" : "text-muted-foreground",
                )}
              >
                {new Date(`${day}T12:00:00`).toLocaleDateString(undefined, {
                  weekday: "short",
                })}
                <span className="ml-1 tabular-nums opacity-70">{day.slice(8)}</span>
              </div>
            ))}
          </div>

          {slots.map((slot) => (
            <div
              key={slot}
              // `flex-1` on every row, so ten slots and fourteen both fill the
              // same grid exactly. `min-h-0` is what lets them shrink below
              // their content instead of forcing the parent to overflow.
              className="grid min-h-0 flex-1 grid-cols-[4rem_repeat(7,minmax(0,1fr))] border-b last:border-b-0"
            >
              <div className="border-r px-2 py-1.5 text-right text-[11px] tabular-nums text-muted-foreground">
                {slot}
              </div>
              {days.map((day) => {
                const cell = byCell.get(`${day}|${slot}`) ?? [];
                return (
                  <div
                    key={day}
                    className={cn(
                      "min-h-0 space-y-1 overflow-hidden border-r p-1 last:border-r-0",
                      day === todayKey() && "bg-muted/20",
                    )}
                  >
                    {cell.map((post) => (
                      <Chip key={post.id} post={post} />
                    ))}
                  </div>
                );
              })}
            </div>
          ))}
        </div>
      </div>

      <p className="shrink-0 text-[11px] text-muted-foreground">
        An empty cell is a slot nothing is booked into. Rows are the times this
        page actually posts at, not every hour of the day.
      </p>
    </div>
  );
}

const TONE: Record<string, string> = {
  PUBLISHED: "border-green-600/30 bg-green-600/10",
  ERROR: "border-red-600/40 bg-red-600/10",
  DRAFT: "border-border bg-muted",
};

function Chip({ post }: { post: ScheduledPost }) {
  const body = (
    <>
      <span className="tabular-nums opacity-60">{post.published_at.slice(11, 16)}</span>{" "}
      {post.text.slice(0, 40) || "No caption"}
    </>
  );

  const className = cn(
    "block w-full truncate rounded border px-1.5 py-1 text-left text-[11px] leading-tight",
    TONE[post.status] ?? "border-border bg-muted",
    // Ours stands out against the old system's, which is what this screen is
    // for during the cutover.
    post.draft_id && "ring-1 ring-gold",
  );

  // Only a published post has somewhere to go. A pending one exists solely in
  // Metricool, and a dead link is worse than none.
  return post.public_url ? (
    <a href={post.public_url} target="_blank" rel="noreferrer" title={post.text} className={cn(className, "hover:bg-muted")}>
      {body}
    </a>
  ) : (
    <span title={post.text} className={className}>
      {body}
    </span>
  );
}

/**
 * The rows: every slot the week actually uses, half-hourly-rounded.
 *
 * Union rather than a fixed list, so a page that changes its posting times
 * changes its grid without anybody editing a constant here. The fallback is for
 * an empty week, which would otherwise render a grid with no rows at all.
 */
function slotRows(posts: ScheduledPost[]): string[] {
  const hours = new Set(posts.map((post) => `${post.published_at.slice(11, 13)}:00`));
  if (hours.size === 0) return ["00:00", "06:00", "12:00", "18:00"];
  return [...hours].sort();
}

/** Posts drift a few minutes off the hour, so they land on their own hour's row. */
function nearestSlot(post: ScheduledPost, slots: string[]): string {
  const hour = `${post.published_at.slice(11, 13)}:00`;
  return slots.includes(hour) ? hour : slots[0];
}

export function startOfWeek(date: Date): Date {
  const start = new Date(date);
  start.setHours(12, 0, 0, 0);
  start.setDate(start.getDate() - start.getDay());
  return start;
}

function shift(date: Date, days: number): Date {
  const next = new Date(date);
  next.setDate(next.getDate() + days);
  return next;
}

/** Local date keys, to match the planner's naive local stamps. */
function weekDays(weekStart: Date): string[] {
  return Array.from({ length: 7 }, (_, index) => key(shift(weekStart, index)));
}

function key(date: Date): string {
  const offset = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 10);
}

/** The Page's today, not the browser's — `key()` is for grid columns, which
 *  are built from `startOfWeek(pageNoon())` and so are already in step. */
function todayKey(): string {
  return pageToday();
}

function label(day: string): string {
  return new Date(`${day}T12:00:00`).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
  });
}
