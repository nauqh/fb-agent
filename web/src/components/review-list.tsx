"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { AlertTriangle, TriangleAlert } from "lucide-react";

import { listDrafts } from "@/lib/api/drafts";
import { timeAgo } from "@/lib/format";
import type { Draft, DraftStatus } from "@/lib/types";
import { useQuery } from "@/lib/use-query";
import { cn } from "@/lib/utils";
import { Skeleton } from "@/components/ui/skeleton";
import { useReviewFilter } from "@/lib/review-filter";

const FILTERS: { value: DraftStatus | "all"; label: string }[] = [
  { value: "review", label: "Needs review" },
  { value: "approved", label: "Approved" },
  { value: "rejected", label: "Rejected" },
  // Its own tab, not folded into "Needs review": a run that produced nothing is
  // not awaiting a decision, and it used to sit in the queue looking ready.
  { value: "failed", label: "Failed" },
  { value: "all", label: "All" },
];

export function ReviewList() {
  const params = useParams<{ id?: string }>();
  const selectedId = params.id ? Number(params.id) : null;
  const { status, setStatus } = useReviewFilter();

  /**
   * `generating` rows are folded into every filter.
   *
   * A run in flight is not "needs review" yet, but hiding it means pressing
   * Generate appears to do nothing — the queue has to show the work arriving.
   */
  const { data: drafts, loading } = useQuery(
    async () => {
      const [matching, generating] = await Promise.all([
        listDrafts({ status }),
        status === "generating" || status === "all"
          ? Promise.resolve([])
          : listDrafts({ status: "generating" }),
      ]);
      return [...generating, ...matching];
    },
    [status],
    {
      intervalMs: 2_000,
      // Only while something is in flight. With a settled queue the store
      // notification is enough, and a timer that never stops keeps the page
      // from ever going idle.
      pollWhile: (rows) => rows === null || rows.some((row) => row.status === "generating"),
    },
  );

  return (
    <div className="flex h-full min-h-0 flex-col rounded-lg border">
      <div className="flex flex-wrap gap-1 border-b p-2">
        {FILTERS.map((filter) => (
          <button
            key={filter.value}
            type="button"
            onClick={() => setStatus(filter.value)}
            className={cn(
              "rounded-md px-2 py-1 text-xs transition-colors",
              status === filter.value
                ? "bg-foreground text-background"
                : "text-muted-foreground hover:bg-muted",
            )}
          >
            {filter.label}
          </button>
        ))}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto p-1.5">
        {loading && !drafts ? (
          <div className="space-y-1.5 p-1">
            {Array.from({ length: 4 }).map((_, index) => (
              <Skeleton key={index} className="h-16 rounded-md" />
            ))}
          </div>
        ) : drafts?.length === 0 ? (
          <p className="px-3 py-10 text-center text-xs text-muted-foreground">
            Queue is empty.
          </p>
        ) : (
          <ul className="space-y-0.5">
            {drafts?.map((draft) => (
              <li key={draft.id}>
                <Row draft={draft} selected={draft.id === selectedId} />
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function Row({ draft, selected }: { draft: Draft; selected: boolean }) {
  const generating = draft.status === "generating";

  return (
    <Link
      href={`/review/${draft.id}`}
      className={cn(
        "block rounded-md px-3 py-2.5 transition-colors",
        selected ? "bg-muted" : "hover:bg-muted/60",
      )}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="font-mono text-[11px] text-muted-foreground">#{draft.id}</span>
        <StatusMark draft={draft} />
      </div>

      <p className="line-clamp-2 pt-1 text-xs leading-snug">
        {generating
          ? (draft.topic ?? "Writing…")
          : (draft.hook ?? draft.topic ?? "Untitled")}
      </p>

      {generating ? (
        <div className="pt-2">
          <div className="h-0.5 w-full overflow-hidden rounded-full bg-border">
            <div
              className="h-full bg-gold transition-[width] duration-500"
              style={{ width: `${draft.progress_pct}%` }}
            />
          </div>
          <p className="pt-1 text-[10px] tabular-nums text-muted-foreground">
            {draft.progress_step} · {draft.progress_pct}%
          </p>
        </div>
      ) : (
        <p className="pt-1 text-[10px] text-muted-foreground">{timeAgo(draft.created_at)}</p>
      )}
    </Link>
  );
}

function StatusMark({ draft }: { draft: Draft }) {
  if (draft.error) {
    return (
      <span className="flex items-center gap-1 text-[10px] text-destructive">
        <TriangleAlert className="size-3" /> error
      </span>
    );
  }
  if (draft.status === "generating") {
    return <span className="size-1.5 animate-pulse rounded-full bg-gold" />;
  }
  if (draft.warnings.length > 0) {
    return (
      <span className="flex items-center gap-1 text-[10px] text-muted-foreground">
        <AlertTriangle className="size-3" /> {draft.warnings.length}
      </span>
    );
  }
  return <span className="text-[10px] text-muted-foreground">{draft.status}</span>;
}
