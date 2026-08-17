"use client";

import { useState } from "react";
import { CalendarDays, List } from "lucide-react";

import { ScheduleList } from "@/components/schedule-list";
import { ScheduleWeek, startOfWeek } from "@/components/schedule-week";
import { Empty } from "@/components/screen";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { getSchedule } from "@/lib/api/schedule";
import { pageNoon } from "@/lib/format";
import { usePageScope } from "@/lib/page-scope";
import { useQuery } from "@/lib/use-query";

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
  const [weekStart, setWeekStart] = useState(() => startOfWeek(pageNoon()));

  const { pageId } = usePageScope();

  const { data: posts, error, loading } = useQuery(
    () => getSchedule(pageId!, 30, 30),
    [pageId],
    {
      enabled: pageId !== null,
      // Somebody else's planner, changing without us. Slow: nothing here is a
      // job in flight being watched.
      intervalMs: 60_000,
    },
  );

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
      {/* The shared pill (`ui/tabs.tsx`) rather than the bordered ghost-button
          pair this was — a custom-built lookalike that missed the pass over
          every other tab control in the app. */}
      <Tabs value={mode} onValueChange={(next) => setMode(next as "week" | "list")}>
        <TabsList className="w-fit shrink-0">
          <TabsTrigger value="week" className="gap-1.5">
            <CalendarDays className="size-3.5" />
            Week
          </TabsTrigger>
          <TabsTrigger value="list" className="gap-1.5">
            <List className="size-3.5" />
            List
          </TabsTrigger>
        </TabsList>
      </Tabs>

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
        // `pr-3` holds the rows off the scrollbar this element owns.
        <div className="min-h-0 flex-1 overflow-y-auto pr-3">
          <ScheduleList posts={posts ?? []} />
        </div>
      )}
    </div>
  );
}
