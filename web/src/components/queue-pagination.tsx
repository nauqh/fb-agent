"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";

import { Button } from "@/components/ui/button";

export const QUEUE_PAGE_SIZE = 10;

/**
 * Pages the queue, as the old app did.
 *
 * The queue rows are tall — a 120px composite each — so a month of drafts is a
 * very long scroll through a shell that is `h-screen` and does not scroll the
 * page. Ten to a page keeps the whole table on screen, which is also what makes
 * the header row worth having: you can compare Status down a column without the
 * column running off the bottom.
 *
 * Absent entirely when everything already fits. A pager under three rows is
 * furniture.
 */
export function QueuePagination({
  totalItems,
  page,
  pageSize = QUEUE_PAGE_SIZE,
  onPageChange,
}: {
  totalItems: number;
  page: number;
  pageSize?: number;
  onPageChange: (page: number) => void;
}) {
  const totalPages = Math.max(1, Math.ceil(totalItems / pageSize));
  const safePage = Math.min(Math.max(page, 1), totalPages);
  const start = totalItems === 0 ? 0 : (safePage - 1) * pageSize + 1;
  const end = Math.min(safePage * pageSize, totalItems);

  if (totalItems <= pageSize) return null;

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-t bg-muted/20 px-4 py-2.5">
      <p className="text-xs text-muted-foreground tabular-nums">
        Showing {start}–{end} of {totalItems}
      </p>
      <div className="flex items-center gap-1">
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="h-8 gap-1"
          disabled={safePage <= 1}
          onClick={() => onPageChange(safePage - 1)}
        >
          <ChevronLeft className="size-4" />
          Previous
        </Button>
        <span className="min-w-[6.5rem] px-2 text-center text-xs text-muted-foreground tabular-nums">
          Page {safePage} of {totalPages}
        </span>
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="h-8 gap-1"
          disabled={safePage >= totalPages}
          onClick={() => onPageChange(safePage + 1)}
        >
          Next
          <ChevronRight className="size-4" />
        </Button>
      </div>
    </div>
  );
}
