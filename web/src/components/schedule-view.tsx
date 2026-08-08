"use client";

import { useState } from "react";
import { CalendarDays, List } from "lucide-react";

import { ScheduleList } from "@/components/schedule-list";
import { ScheduleWeek, startOfWeek } from "@/components/schedule-week";
import { Empty } from "@/components/screen";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { getSchedule } from "@/lib/api/schedule";
import { useQuery } from "@/lib/use-query";
import { cn } from "@/lib/utils";

/**
 * Week or list, over one fetch.
 *
 * The window is deliberately wider than either view shows — 30 days back and 30
 * ahead — so paging between weeks is instant and does not re-hit somebody else's
 * API for every arrow press. About 500 rows at this page's rate, which is a few
 * hundred KB and cheaper than the round trip.
 */
export function ScheduleView() {
  const [mode, setMode] = useState<"week" | "list">("week");
  const [weekStart, setWeekStart] = useState(() => startOfWeek(new Date()));

  const { data: posts, error, loading } = useQuery(() => getSchedule(30, 30), [], {
    // Somebody else's planner, changing without us. Slow: nothing here is a job
    // in flight being watched.
    intervalMs: 60_000,
  });

  if (error) {
    return (
      <Empty>
        Could not reach Metricool&apos;s planner. {error}
        <br />
        Nothing is cached — the planner is the only record of what is scheduled.
      </Empty>
    );
  }

  if (loading && !posts) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 6 }).map((_, index) => (
          <Skeleton key={index} className="h-16 rounded-lg" />
        ))}
      </div>
    );
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4">
      <div className="flex w-fit shrink-0 gap-1 rounded-lg border p-1">
        {(["week", "list"] as const).map((value) => (
          <Button
            key={value}
            variant="ghost"
            size="sm"
            onClick={() => setMode(value)}
            className={cn("gap-1.5", mode === value && "bg-muted")}
          >
            {value === "week" ? (
              <CalendarDays className="size-3.5" />
            ) : (
              <List className="size-3.5" />
            )}
            {value === "week" ? "Week" : "List"}
          </Button>
        ))}
      </div>

      {/*
        The two views want opposite things from the space they are given.

        The week is a shape — seven columns you compare against each other — so
        it has to be *whole*, and it sizes its rows to whatever height is left
        rather than scrolling. A grid you scroll is a grid you cannot compare
        across, which is the only reason to draw one.

        The list is a sequence, and there is no reading it without scrolling, so
        it scrolls inside itself and leaves the header and toggle in place.
      */}
      {mode === "week" ? (
        <ScheduleWeek
          posts={posts ?? []}
          weekStart={weekStart}
          onWeekChange={setWeekStart}
        />
      ) : (
        <div className="min-h-0 flex-1 overflow-y-auto">
          <ScheduleList posts={posts ?? []} />
        </div>
      )}
    </div>
  );
}
