"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { AlertTriangle, Check, Loader2, TriangleAlert, X } from "lucide-react";
import { toast } from "sonner";

import { approveDraft, listDrafts, rejectDraft } from "@/lib/api/drafts";
import { timeAgo } from "@/lib/format";
import type { Draft, DraftStatus } from "@/lib/types";
import { useQuery } from "@/lib/use-query";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
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

/**
 * The queue: one table, one row per draft, click a row to open it.
 *
 * A table rather than cards, which is what the old app used and is the right
 * shape for the job — the columns line up, so you scan *down* Status or Created
 * instead of hunting for them inside each tile. Cards spread eight drafts over a
 * screen that a table fits in a third of.
 *
 * The columns are the old app's minus Page, which had a filter dropdown there
 * because it ran ten brands. v1 runs one, so the column would be the same value
 * repeated down the page.
 */
export function ReviewList() {
  const { status, setStatus } = useReviewFilter();

  /**
   * `generating` rows are folded into every filter.
   *
   * A run in flight is not "needs review" yet, but hiding it means pressing
   * Generate appears to do nothing — the queue has to show the work arriving.
   */
  const { data: drafts, loading, refresh } = useQuery(
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
    <div className="flex min-h-0 flex-1 flex-col gap-3">
      <div className="flex flex-wrap gap-1">
        {FILTERS.map((filter) => (
          <button
            key={filter.value}
            type="button"
            onClick={() => setStatus(filter.value)}
            className={cn(
              "rounded-md px-2.5 py-1 text-xs transition-colors",
              status === filter.value
                ? "bg-foreground text-background"
                : "text-muted-foreground hover:bg-muted",
            )}
          >
            {filter.label}
          </button>
        ))}
      </div>

      {/* Hugs its rows. A `flex-1` container left a tall empty bordered box
          under a two-draft queue, which read as something failing to load. */}
      <div className="overflow-hidden rounded-xl border">
        {loading && !drafts ? (
          <div className="space-y-2 p-4">
            {Array.from({ length: 5 }).map((_, index) => (
              <Skeleton key={index} className="h-28 rounded-lg" />
            ))}
          </div>
        ) : drafts?.length === 0 ? (
          <p className="py-20 text-center text-sm text-muted-foreground">Queue is empty.</p>
        ) : (
          <table className="w-full min-w-[860px]">
            <thead>
              <tr className="border-b bg-muted/30 text-left text-[11px] uppercase tracking-wide text-muted-foreground">
                <th className="w-32 px-5 py-3 font-medium">
                  <span className="sr-only">Image</span>
                </th>
                <th className="px-2 py-3 font-medium">Post</th>
                {/* Status and Created sit together at the right rather than in
                    two spread-out columns. On a wide screen they used to drift
                    so far from the row they read as unrelated. */}
                <th className="w-56 px-5 py-3 font-medium">Status</th>
                <th className="w-24 px-5 py-3 text-right font-medium">
                  <span className="sr-only">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {drafts?.map((draft) => (
                <Row key={draft.id} draft={draft} onDecided={refresh} />
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

function Row({ draft, onDecided }: { draft: Draft; onDecided: () => void }) {
  const router = useRouter();
  const [deciding, setDeciding] = useState(false);
  const generating = draft.status === "generating";

  async function decide(action: "approve" | "reject") {
    setDeciding(true);
    try {
      if (action === "approve") await approveDraft(draft.id);
      else await rejectDraft(draft.id);
      toast(action === "approve" ? `Approved #${draft.id}.` : `Rejected #${draft.id}.`);
      onDecided();
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "Action failed");
    } finally {
      setDeciding(false);
    }
  }

  return (
    <tr
      className={cn("group", generating ? "bg-muted/10" : "cursor-pointer hover:bg-muted/30")}
      onClick={generating ? undefined : () => router.push(`/review/${draft.id}`)}
    >
      <td className="px-5 py-4 align-top">
        {/* The composite at a size you can actually judge. It is the product —
            a 48px chip of it told you a picture existed and nothing else. 4:5
            whether or not one has been drawn, so rows keep their height as
            pictures arrive. */}
        <div className="aspect-[4/5] w-[88px] overflow-hidden rounded-lg border bg-muted shadow-sm">
          {draft.composed_image_path ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={`/api/media/${draft.composed_image_path}`}
              alt=""
              className="size-full object-cover"
            />
          ) : generating ? (
            <div className="flex size-full items-center justify-center">
              <Loader2 className="size-4 animate-spin text-muted-foreground" />
            </div>
          ) : null}
        </div>
      </td>

      {/* `max-w-0` is what makes the clamps work: without it the cell grows to
          fit the text and nothing ever truncates. */}
      <td className="max-w-0 px-2 py-4 align-middle">
        {/* The hook only. The old app's second line was the brand label, which
            on a one-page install is the same string on every row; the caption
            went there instead and turned the queue into a wall of body text you
            have to read past to find the post you want. */}
        <p className="line-clamp-2 text-[15px] font-medium leading-snug">
          {generating ? (draft.topic ?? "Writing…") : (draft.hook ?? draft.topic ?? "Untitled")}
        </p>
        {generating ? (
          <div className="mt-3 flex items-center gap-2">
            <div className="h-1 w-40 overflow-hidden rounded-full bg-border">
              <div
                className="h-full bg-gold transition-[width] duration-500"
                style={{ width: `${draft.progress_pct}%` }}
              />
            </div>
            <span className="text-xs tabular-nums text-muted-foreground">
              {draft.progress_step} · {draft.progress_pct}%
            </span>
          </div>
        ) : null}
      </td>

      {/* Status over the timestamp, in one block. Two spread columns put them
          at opposite ends of a wide row and neither read as belonging to it. */}
      <td className="px-5 py-4 align-middle">
        <div className="flex flex-wrap items-center gap-1.5">
          <StatusBadge draft={draft} />
          {draft.warnings.length > 0 ? (
            <span className="inline-flex items-center gap-1 rounded-md border border-gold/40 bg-gold/10 px-1.5 py-0.5 text-[11px]">
              <AlertTriangle className="size-3" />
              {draft.warnings.length}
            </span>
          ) : null}
        </div>
        <p className="mt-1.5 whitespace-nowrap text-[13px] text-muted-foreground">
          {timeAgo(draft.created_at)}
        </p>
      </td>

      {/* Draining the queue is the common case, so Approve and Reject are here
          as well as in the sheet. `stopPropagation` keeps a decision from also
          opening the draft it just removed. */}
      <td className="px-5 py-4 align-middle text-right" onClick={(event) => event.stopPropagation()}>
        {draft.status === "review" ? (
          <div className="flex items-center justify-end gap-1 opacity-0 transition-opacity group-hover:opacity-100 focus-within:opacity-100">
            <Button
              variant="ghost"
              size="icon"
              disabled={deciding}
              onClick={() => void decide("reject")}
              title="Reject"
            >
              <X className="size-4" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="text-gold hover:bg-gold/10 hover:text-gold"
              disabled={deciding}
              onClick={() => void decide("approve")}
              title="Approve"
            >
              {deciding ? <Loader2 className="size-4 animate-spin" /> : <Check className="size-4" />}
            </Button>
          </div>
        ) : null}
      </td>
    </tr>
  );
}

function StatusBadge({ draft }: { draft: Draft }) {
  if (draft.error) {
    return (
      <span className="inline-flex items-center gap-1 rounded border border-destructive/40 bg-destructive/10 px-1.5 py-0.5 text-[11px] text-destructive">
        <TriangleAlert className="size-3" />
        failed
      </span>
    );
  }
  return (
    <span
      className={cn(
        "rounded border px-1.5 py-0.5 text-[11px]",
        draft.status === "generating" && "border-gold/40 bg-gold/10",
        draft.status === "review" && "border-foreground/20 bg-foreground/5",
        (draft.status === "approved" || draft.status === "rejected") &&
          "border-transparent bg-muted text-muted-foreground",
      )}
    >
      {draft.status}
    </span>
  );
}
