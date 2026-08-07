"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  Loader2,
  MoreHorizontal,
  Pencil,
  Rocket,
  Trash2,
  X,
} from "lucide-react";
import { toast } from "sonner";

import { deleteDraft, listDrafts, rejectDraft } from "@/lib/api/drafts";
import { listPages } from "@/lib/api/pages";
import { fullDate } from "@/lib/format";
import type { Draft, Page } from "@/lib/types";
import { useQuery } from "@/lib/use-query";
import { cn } from "@/lib/utils";
import { ViewFullButton } from "@/components/image-lightbox";
import { PageBadge } from "@/components/page-badge";
import { QUEUE_PAGE_SIZE, QueuePagination } from "@/components/queue-pagination";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
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
  const [page, setPage] = useState(1);

  /**
   * `generating` rows are folded into every filter.
   *
   * A run in flight is not "needs review" yet, but hiding it means pressing
   * Generate appears to do nothing — the queue has to show the work arriving.
   */
  const { data: drafts, loading, refresh } = useQuery(
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

  const total = drafts?.length ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / QUEUE_PAGE_SIZE));
  const safePage = Math.min(page, totalPages);
  const shown = useMemo(
    () => drafts?.slice((safePage - 1) * QUEUE_PAGE_SIZE, safePage * QUEUE_PAGE_SIZE) ?? [],
    [drafts, safePage],
  );

  // Rejecting the last draft on the last page would otherwise strand the queue
  // on a page that no longer exists.
  useEffect(() => {
    if (page > totalPages) setPage(totalPages);
  }, [page, totalPages]);

  return (
    // Not `flex-1`: the shell is `h-screen` and does not scroll the page, so a
    // `flex-1` list sized itself to the viewport and never overflowed — while
    // the bordered container's `overflow-hidden` quietly clipped every row past
    // the fold. Nothing scrolled and nothing said so. Sized to its content, the
    // layout's own `overflow-y-auto` has something to scroll.
    <div className="flex flex-col gap-3">

      {/* Hugs its rows. A `flex-1` container left a tall empty bordered box
          under a two-draft queue, which read as something failing to load. */}
      <div className="overflow-hidden rounded-xl border">
        {loading && !drafts ? (
          <div className="space-y-2 p-4">
            {Array.from({ length: 5 }).map((_, index) => (
              <Skeleton key={index} className="h-20 rounded-lg" />
            ))}
          </div>
        ) : drafts?.length === 0 ? (
          <p className="py-20 text-center text-sm text-muted-foreground">Queue is empty.</p>
        ) : (
          <table className="w-full min-w-[980px]">
            <thead>
              <tr className="border-b bg-muted/30 text-left text-[11px] uppercase tracking-wide text-muted-foreground">
                <th className="w-24 px-5 py-3 font-medium">
                  <span className="sr-only">Image</span>
                </th>
                <th className="px-2 py-3 font-medium">Post</th>
                <th className="w-56 px-5 py-3 font-medium">Page</th>
                <th className="w-44 px-5 py-3 font-medium">Created</th>
                <th className="w-40 px-5 py-3 font-medium">Status</th>
                <th className="w-16 px-5 py-3 text-right font-medium">
                  <span className="sr-only">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {shown.map((draft) => (
                <Row
                  key={draft.id}
                  draft={draft}
                  page={pages?.find((candidate) => candidate.id === draft.page_id)}
                  onChanged={refresh}
                />
              ))}
            </tbody>
          </table>
        )}

        <QueuePagination totalItems={total} page={safePage} onPageChange={setPage} />
      </div>
    </div>
  );
}

function Row({
  draft,
  page,
  onChanged,
}: {
  draft: Draft;
  page?: Page;
  onChanged: () => void;
}) {
  const router = useRouter();
  const generating = draft.status === "generating";

  return (
    <tr
      className={cn("group", generating ? "bg-muted/10" : "cursor-pointer hover:bg-muted/30")}
      onClick={generating ? undefined : () => router.push(`/review/${draft.id}`)}
    >
      <td className="px-5 py-4 align-top">
        {/* Big enough to recognise the post, small enough that ten rows fit a
            screen. 120px made each row taller than the text it carried; the eye
            button opens it full size when the composite itself is the question.
            4:5 whether or not one has been drawn, so rows keep their height as
            pictures arrive. */}
        <div className="group/thumb relative aspect-[4/5] w-[72px] overflow-hidden rounded-lg border bg-muted shadow-sm">
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
            // The empty frame is where the eye goes, so it says what it is
            // waiting for rather than spinning anonymously.
            <div className="flex size-full flex-col items-center justify-center gap-2 px-2 text-center">
              <Loader2 className="size-4 animate-spin text-muted-foreground" />
              <span className="text-[10px] leading-tight text-muted-foreground">
                {draft.progress_pct >= 60 ? "Drawing the image" : "Writing the post"}
              </span>
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

      {/* The row opens the draft; this must not, so every branch stops the
          click before it reaches the <tr>. */}
      <td className="px-5 py-4 align-middle text-right" onClick={(e) => e.stopPropagation()}>
        {generating ? null : <RowMenu draft={draft} onChanged={onChanged} />}
      </td>
    </tr>
  );
}

function RowMenu({ draft, onChanged }: { draft: Draft; onChanged: () => void }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [confirming, setConfirming] = useState(false);

  async function run(work: () => Promise<unknown>, done: string) {
    setBusy(true);
    try {
      await work();
      toast(done);
      onChanged();
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "Action failed");
    } finally {
      setBusy(false);
      setConfirming(false);
    }
  }

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            variant="ghost"
            size="icon-sm"
            disabled={busy}
            aria-label="Actions"
            className="opacity-0 transition-opacity group-hover:opacity-100 focus-visible:opacity-100 data-[state=open]:opacity-100"
          >
            {busy ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <MoreHorizontal className="size-4" />
            )}
          </Button>
        </DropdownMenuTrigger>

        <DropdownMenuContent>
          <DropdownMenuItem onSelect={() => router.push(`/review/${draft.id}`)}>
            <Pencil className="size-4" />
            Review
          </DropdownMenuItem>

          {/* Disabled rather than hidden: publishing is the point of the whole
              app and its absence is worth stating. Nothing pushes to Facebook
              in v1 — the old system still does that. */}
          <DropdownMenuItem
            disabled
            title="Not in v1 — the old system still publishes."
          >
            <Rocket className="size-4" />
            Publish now
          </DropdownMenuItem>

          <DropdownMenuSeparator />

          {draft.status === "rejected" ? null : (
            <DropdownMenuItem
              destructive
              onSelect={() => void run(() => rejectDraft(draft.id), "Rejected.")}
            >
              <X className="size-4" />
              Reject
            </DropdownMenuItem>
          )}

          <DropdownMenuItem
            destructive
            onSelect={(event) => {
              // The menu closes on select, so the dialog has to be opened after
              // it goes rather than from inside it.
              event.preventDefault();
              setConfirming(true);
            }}
          >
            <Trash2 className="size-4" />
            Delete
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      {/* Reject is undoable and needs no ceremony. Delete removes the row and
          both pictures with no way back, so it asks first. */}
      <Dialog open={confirming} onOpenChange={setConfirming}>
        <DialogContent className="sm:max-w-md">
          <DialogTitle>Delete this draft?</DialogTitle>
          <DialogDescription>
            The draft and its images are removed for good. Reject instead if you
            only want it out of the queue.
          </DialogDescription>
          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => setConfirming(false)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              disabled={busy}
              onClick={() => void run(() => deleteDraft(draft.id), "Deleted.")}
            >
              {busy ? <Loader2 className="size-4 animate-spin" /> : <Trash2 className="size-4" />}
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

/**
 * A pill per status: plain green, plain red, white type.
 *
 * Several versions on the way here, and the failures rhyme. An alpha tint over
 * white and a pale 50/800 pair both read as *nearly* a colour — washed out
 * rather than green — while a bare outline was too faint to scan down a column.
 * A flat 600 fill is simply the colour it claims to be.
 *
 * A queue is mostly one status, so whatever the majority looks like becomes the
 * texture of the whole screen. That is why Pending review and Rejected are
 * neutral grey, and colour is spent only on the two worth stopping for: green
 * for the one end state that is good, red for the one that lost work.
 *
 * Keyed on `status`, never on `error`. A row the startup sweep touched while
 * its task was still running kept a stale error string, and an earlier version
 * of this rendered a finished draft as failed on the strength of it.
 */
const STATUS: Record<string, { label: string; className: string }> = {
  generating: {
    label: "Generating",
    className: "border-border bg-muted text-muted-foreground",
  },
  review: {
    label: "Pending review",
    className: "border-border bg-muted text-foreground",
  },
  approved: {
    label: "Approved",
    className: "border-transparent bg-green-600 text-white",
  },
  rejected: {
    label: "Rejected",
    className: "border-border bg-muted text-muted-foreground",
  },
  failed: {
    label: "Failed",
    className: "border-transparent bg-red-600 text-white",
  },
};

function StatusBadge({ draft }: { draft: Draft }) {
  const tone = STATUS[draft.status] ?? {
    label: draft.status,
    className: "border-border text-muted-foreground",
  };

  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium",
        tone.className,
      )}
    >
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
