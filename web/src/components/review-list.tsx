"use client";

import { useRouter } from "next/navigation";
import { AlertTriangle, Loader2, TriangleAlert } from "lucide-react";

import { listDrafts } from "@/lib/api/drafts";
import { listPages } from "@/lib/api/pages";
import { fullDate } from "@/lib/format";
import type { Draft, Page } from "@/lib/types";
import { useQuery } from "@/lib/use-query";
import { cn } from "@/lib/utils";
import { ViewFullButton } from "@/components/image-lightbox";
import { PageBadge } from "@/components/page-badge";
import { Skeleton } from "@/components/ui/skeleton";

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
  const { data: pages } = useQuery(() => listPages(), []);

  /**
   * `generating` rows are folded into every filter.
   *
   * A run in flight is not "needs review" yet, but hiding it means pressing
   * Generate appears to do nothing — the queue has to show the work arriving.
   */
  const { data: drafts, loading } = useQuery(
    () => listDrafts(),
    [],
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
          <table className="w-full min-w-[980px]">
            <thead>
              <tr className="border-b bg-muted/30 text-left text-[11px] uppercase tracking-wide text-muted-foreground">
                <th className="w-36 px-5 py-3 font-medium">
                  <span className="sr-only">Image</span>
                </th>
                <th className="px-2 py-3 font-medium">Post</th>
                <th className="w-56 px-5 py-3 font-medium">Page</th>
                <th className="w-44 px-5 py-3 font-medium">Created</th>
                <th className="w-40 px-5 py-3 font-medium">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {drafts?.map((draft) => (
                <Row
                  key={draft.id}
                  draft={draft}
                  page={pages?.find((candidate) => candidate.id === draft.page_id)}
                />
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

function Row({ draft, page }: { draft: Draft; page?: Page }) {
  const router = useRouter();
  const generating = draft.status === "generating";

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
        <div className="group/thumb relative aspect-[4/5] w-[120px] overflow-hidden rounded-lg border bg-muted shadow-sm">
          {draft.composed_image_path ? (
            <>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={`/api/media/${draft.composed_image_path}`}
                alt=""
                className="size-full object-cover"
              />
              <ViewFullButton
                src={`/api/media/${draft.composed_image_path}`}
                alt={`Draft ${draft.id} composed image`}
              />
            </>
          ) : generating ? (
            <div className="flex size-full items-center justify-center">
              <Loader2 className="size-4 animate-spin text-muted-foreground" />
            </div>
          ) : null}
        </div>
      </td>


      {/* Title over the page name, as the old app had it. The title is the
          hook's first sentence: the writer produces no separate one, and the
          whole 65-word hook is a paragraph, not a row label. */}
      <td className="max-w-0 px-2 py-4 align-middle">
        <p className="line-clamp-1 text-[15px] font-medium leading-snug">{title(draft)}</p>
        <p className="mt-0.5 line-clamp-1 text-[13px] text-muted-foreground">
          {page?.name ?? ""}
        </p>
      </td>

      {/* Page, Created and Status as their own columns, which is the old app's
          layout. They line up down the queue, which is the point of a table. */}
      <td className="px-5 py-4 align-middle">
        <PageBadge
          name={page?.name ?? ""}
          avatarPath={page?.avatar_image_path}
          className="text-[13px]"
        />
      </td>

      <td className="whitespace-nowrap px-5 py-4 align-middle text-[13px] text-muted-foreground">
        {fullDate(draft.created_at)}
      </td>

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
        {generating ? (
          <div className="mt-2 w-40">
            <div className="h-1 overflow-hidden rounded-full bg-border">
              <div
                className="h-full bg-gold transition-[width] duration-500"
                style={{ width: `${draft.progress_pct}%` }}
              />
            </div>
            <p className="pt-1 text-[11px] tabular-nums text-muted-foreground">
              {draft.progress_step} · {draft.progress_pct}%
            </p>
          </div>
        ) : null}
      </td>

    </tr>
  );
}

/**
 * A pill per status, coloured by what it means rather than decoratively.
 *
 * Amber is the queue itself — the thing this screen exists for — so it draws
 * the eye. Green is the only end state that is good; red is the only one that
 * lost work. Rejected is deliberately grey: a decision that was made, not a
 * problem to fix.
 *
 * Keyed on `status`, never on `error`. A row the startup sweep touched while
 * its task was still running kept a stale error string, and an earlier version
 * of this rendered a finished draft as failed on the strength of it.
 */
const STATUS: Record<string, { label: string; className: string }> = {
  generating: {
    label: "Generating",
    className: "border-blue-500/30 bg-blue-500/10 text-blue-700 dark:text-blue-300",
  },
  review: {
    label: "Pending review",
    className: "border-amber-500/30 bg-amber-500/15 text-amber-700 dark:text-amber-300",
  },
  approved: {
    label: "Approved",
    className: "border-emerald-500/30 bg-emerald-500/15 text-emerald-700 dark:text-emerald-300",
  },
  rejected: {
    label: "Rejected",
    className: "border-transparent bg-muted text-muted-foreground",
  },
  failed: {
    label: "Failed",
    className: "border-destructive/30 bg-destructive/10 text-destructive",
  },
};

function StatusBadge({ draft }: { draft: Draft }) {
  const tone = STATUS[draft.status] ?? {
    label: draft.status,
    className: "border-border bg-muted text-muted-foreground",
  };

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs font-medium",
        tone.className,
      )}
    >
      {draft.status === "failed" ? <TriangleAlert className="size-3" /> : null}
      {tone.label}
    </span>
  );
}

/** The hook is a paragraph; a row wants its first sentence. */
function title(draft: Draft): string {
  const source = draft.hook ?? draft.topic ?? "";
  if (!source) return "Untitled";
  const [first] = source.split(/(?<=[.!?])\s/);
  return (first ?? source).trim();
}
