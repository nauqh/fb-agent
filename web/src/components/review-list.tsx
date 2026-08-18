"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
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

import {
  deleteDraft,
  listDrafts,
  publishDraft,
  publishMode,
  rejectDraft,
} from "@/lib/api/drafts";
import { dayHeading, dayKey, pageLocalSoon, timeOfDay } from "@/lib/format";
import { usePageScope } from "@/lib/page-scope";
import type { Draft, Page } from "@/lib/types";
import { useQuery } from "@/lib/use-query";
import { pageAvatarRaw } from "@/lib/page-avatar";
import { cn } from "@/lib/utils";
import { ViewFullButton } from "@/components/image-lightbox";
import { PageBadge } from "@/components/page-badge";
import { PublishAt } from "@/components/publish-at";
import { Loading } from "@/components/loading";
import { PublishDialog } from "@/components/publish-dialog";
import { StatusPill, type StatusTone } from "@/components/status-pill";
import {
  QUEUE_PAGE_SIZE,
  QueuePagination,
} from "@/components/queue-pagination";
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

/**
 * The queue: one table, one row per draft, click a row to open it.
 *
 * A table rather than cards, which is what the old app used and is the right
 * shape for the job — the columns line up, so you scan *down* Status or Created
 * instead of hunting for them inside each tile. Cards spread eight drafts over a
 * screen that a table fits in a third of.
 *
 * The columns are the old app's minus Page, which had a filter dropdown there
 * because it ran ten brands. That reasoning outlived the one-Page assumption it
 * was written under: the queue is scoped to the switcher's Page, so the column
 * is still one value repeated down the table, and the filter it would need is
 * already in the header.
 */
export function ReviewList() {
  // `page`/`setPage` below is the *pagination* page. The Page is `pageId`.
  const { pages, pageId } = usePageScope();
  const [page, setPage] = useState(1);

  /**
   * `generating` rows are folded into every filter.
   *
   * A run in flight is not "needs review" yet, but hiding it means pressing
   * Generate appears to do nothing — the queue has to show the work arriving.
   */
  const { data: drafts, refresh } = useQuery(() => listDrafts({ page_id: pageId! }), [pageId], {
    enabled: pageId !== null,
    intervalMs: 2_000,
    // Only while something is in flight. With a settled queue the store
    // notification is enough, and a timer that never stops keeps the page
    // from ever going idle.
    pollWhile: (rows) =>
      rows === null || rows.some((row) => row.status === "generating"),
  });

  /**
   * Whether Publish reaches an audience. Fetched here and passed down, not read
   * per row: `useQuery` holds no cache and re-runs on every store notification,
   * so a hook inside `RowMenu` would be one request per visible draft on every
   * mutation. It is a per-environment constant either way.
   */
  const { data: mode } = useQuery(() => publishMode(), []);

  const total = drafts?.length ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / QUEUE_PAGE_SIZE));
  const safePage = Math.min(page, totalPages);
  const shown = useMemo(
    () =>
      drafts?.slice(
        (safePage - 1) * QUEUE_PAGE_SIZE,
        safePage * QUEUE_PAGE_SIZE,
      ) ?? [],
    [drafts, safePage],
  );

  /**
   * Rejecting the last draft on the last page would otherwise strand the queue
   * on a page that no longer exists.
   *
   * Adjusted during render rather than in an effect — the same correction
   * `use-query.ts` makes when its key changes, and for the same reason. React
   * re-runs the component before committing, so the clamp costs no extra
   * paint, where an effect sets state *after* one and lands a second render.
   *
   * `safePage` below already keeps the *render* honest on its own. This exists
   * so the stored page cannot sit out of range: reject down to one page while
   * on page five, and a later run that grows the queue back to five would
   * otherwise jump the operator there without being asked.
   */
  if (page > totalPages) setPage(totalPages);

  return (
    // Not `flex-1`: the shell is `h-screen` and does not scroll the page, so a
    // `flex-1` list sized itself to the viewport and never overflowed — while
    // the bordered container's `overflow-hidden` quietly clipped every row past
    // the fold. Nothing scrolled and nothing said so. Sized to its content, the
    // layout's own `overflow-y-auto` has something to scroll.
    <div className="flex flex-col gap-3">
      {/* Hugs its rows. A `flex-1` container left a tall empty bordered box
          under a two-draft queue, which read as something failing to load. */}
      <div className="overflow-hidden rounded-lg border">
        {!drafts ? (
          // `!drafts`, not `loading && !drafts` — that test drew a header row
          // over nothing while the Page scope resolved. `use-query.ts` reports
          // `loading` honestly now and would do here too; this stays because
          // "no rows to draw" is the condition this branch is actually about.
          <Loading label="Loading the queue" className="h-72" />
        ) : drafts.length === 0 ? (
          <p className="py-20 text-center text-sm text-muted-foreground">
            Queue is empty.
          </p>
        ) : (
          <table className="w-full min-w-[980px]">
            <thead>
              <tr className="border-b bg-muted/30 text-left font-mono text-[11px] uppercase tracking-[0.12em] text-muted-foreground">
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
            {/*
              A `tbody` per day, which is what the element is for — a table may
              hold several, and each gets its own heading row without breaking
              the column alignment that makes this a table rather than cards.

              Grouping happens *within* the page, not across the queue. A day
              can therefore straddle two pages, and that is the right trade:
              paging by day would make page size depend on how much was
              generated that day, and one heavy batch would be a single
              enormous page.
            */}
            {groupByDay(shown).map(([day, rows]) => (
              <tbody key={day} className="divide-y">
                <tr className="border-b bg-muted/20">
                  <td
                    colSpan={6}
                    className="px-5 py-1.5 font-mono text-[11px] font-medium uppercase tracking-[0.12em] text-muted-foreground"
                  >
                    {dayHeading(rows[0].created_at)}
                    <span className="ml-2 font-normal tabular-nums opacity-70">
                      {rows.length} draft{rows.length === 1 ? "" : "s"}
                    </span>
                  </td>
                </tr>

                {rows.map((draft) => (
                  <Row
                    key={draft.id}
                    draft={draft}
                    page={pages?.find(
                      (candidate) => candidate.id === draft.page_id,
                    )}
                    onChanged={refresh}
                    rehearsal={mode?.rehearsal ?? false}
                  />
                ))}
              </tbody>
            ))}
          </table>
        )}

        <QueuePagination
          totalItems={total}
          page={safePage}
          onPageChange={setPage}
        />
      </div>
    </div>
  );
}

/** Consecutive runs, not a map: the queue is already sorted newest first. */
function groupByDay(drafts: Draft[]): [string, Draft[]][] {
  const days: [string, Draft[]][] = [];
  for (const draft of drafts) {
    const key = dayKey(draft.created_at);
    const last = days[days.length - 1];
    if (last && last[0] === key) last[1].push(draft);
    else days.push([key, [draft]]);
  }
  return days;
}

function Row({
  draft,
  page,
  onChanged,
  rehearsal,
}: {
  draft: Draft;
  page?: Page;
  onChanged: () => void;
  /** Publish only reaches the planner. Threaded from `ReviewList`, not fetched. */
  rehearsal: boolean;
}) {
  const router = useRouter();
  const generating = draft.status === "generating";

  return (
    <tr
      className={cn(
        "group",
        generating ? "bg-muted/10" : "cursor-pointer hover:bg-muted/30",
      )}
      onClick={
        generating ? undefined : () => router.push(`/review/${draft.id}`)
      }
    >
      <td className="px-5 py-4 align-top">
        {/* Big enough to recognise the post, small enough that ten rows fit a
            screen. 120px made each row taller than the text it carried; the eye
            button opens it full size when the composite itself is the question.
            4:5 whether or not one has been drawn, so rows keep their height as
            pictures arrive. */}
        <div className="group/thumb relative aspect-[4/5] w-[72px] overflow-hidden rounded-lg border bg-muted shadow-sm">
          {draft.composed_image_url ? (
            <>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={draft.composed_image_url}
                alt=""
                className="size-full object-cover"
              />
              <ViewFullButton
                src={draft.composed_image_url}
                alt={`Draft ${draft.id} composed image`}
              />
            </>
          ) : generating ? (
            // The empty frame is where the eye goes, so it says what it is
            // waiting for rather than spinning anonymously.
            <div className="flex size-full flex-col items-center justify-center gap-2 px-2 text-center">
              <Loader2 className="size-4 animate-spin text-muted-foreground" />
              <span className="text-[10px] leading-tight text-muted-foreground">
                {draft.progress_pct >= 60
                  ? "Drawing the image"
                  : "Writing the post"}
              </span>
            </div>
          ) : null}
        </div>
      </td>

      {/* Title over the page name, as the old app had it. The title is the
          hook's first sentence: the writer produces no separate one, and the
          whole 65-word hook is a paragraph, not a row label. */}
      <td className="max-w-0 px-2 py-4 align-middle">
        <p className="line-clamp-1 text-[15px] font-medium leading-snug">
          {title(draft)}
        </p>
        <p className="mt-0.5 line-clamp-1 text-[13px] text-muted-foreground">
          {page?.name ?? ""}
        </p>
      </td>

      {/* Page, Created and Status as their own columns, which is the old app's
          layout. They line up down the queue, which is the point of a table. */}
      <td className="px-5 py-4 align-middle">
        <PageBadge
          name={page?.name ?? ""}
          avatarPath={page ? pageAvatarRaw(page) : null}
          className="text-[13px]"
        />
      </td>

      {/* Time only: the date is stated once by the day heading above, and
          repeating it on every row is the column reading the same string
          twenty times. */}
      <td className="whitespace-nowrap px-5 py-4 align-middle text-[13px] tabular-nums text-muted-foreground">
        {timeOfDay(draft.created_at)}
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
            <p className="pt-1 font-mono text-[11px] tabular-nums text-muted-foreground">
              {draft.progress_step} · {draft.progress_pct}%
            </p>
          </div>
        ) : null}
      </td>

      {/* The row opens the draft; this must not, so every branch stops the
          click before it reaches the <tr>. */}
      <td
        className="px-5 py-4 align-middle text-right"
        onClick={(e) => e.stopPropagation()}
      >
        {generating ? null : (
          <RowMenu draft={draft} onChanged={onChanged} rehearsal={rehearsal} />
        )}
      </td>
    </tr>
  );
}

function RowMenu({
  draft,
  onChanged,
  rehearsal,
}: {
  draft: Draft;
  onChanged: () => void;
  rehearsal: boolean;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [when, setWhen] = useState(pageLocalSoon);

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
      setPublishing(false);
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

          {draft.metricool_post_id ? (
            <DropdownMenuItem
              disabled
              title="Change it in Metricool's planner."
            >
              <Rocket className="size-4" />
              In Metricool
            </DropdownMenuItem>
          ) : (
            <DropdownMenuItem
              disabled={draft.status === "failed" || !draft.composed_image_path}
              onSelect={(event) => {
                event.preventDefault();
                setPublishing(true);
              }}
            >
              <Rocket className="size-4" />
              Publish now
            </DropdownMenuItem>
          )}

          <DropdownMenuSeparator />

          {draft.status === "rejected" ? null : (
            <DropdownMenuItem
              destructive
              onSelect={() =>
                void run(() => rejectDraft(draft.id), "Rejected.")
              }
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

      {/* A row has no footer to hold the field, so here it is the dialog's
          content rather than a confirmation of something already chosen. The
          drawer, which does have a footer, puts it there instead. */}
      <PublishDialog
        open={publishing}
        onOpenChange={(next) => {
          // Re-seeded rather than kept: a menu left open while the operator did
          // something else would otherwise offer a time that has since passed.
          if (!next) setWhen(pageLocalSoon());
          setPublishing(next);
        }}
        busy={busy}
        onConfirm={() =>
          void run(
            () => publishDraft(draft.id, when || undefined),
            rehearsal
              ? "Handed to Metricool as a draft. It will not publish."
              : "Handed to Metricool.",
          )
        }
      >
        <PublishAt value={when} onChange={setWhen} />

        {/* Before the press. The row menu is the fast path — the drawer at
            least shows the post first — so this is the one that most needs to
            say what the button does. */}
        {rehearsal ? (
          <p className="text-sm font-medium text-amber-700 dark:text-amber-400">
            Rehearsal mode. This lands in the planner as a draft and will not
            reach the page.
          </p>
        ) : null}
      </PublishDialog>

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
              {busy ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <Trash2 className="size-4" />
              )}
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

/**
 * The look lives in `components/status-pill.tsx`, shared with the Schedule.
 * What stays here is which draft status means what.
 *
 * Keyed on `status`, never on `error`. A row the startup sweep touched while
 * its task was still running kept a stale error string, and an earlier version
 * of this rendered a finished draft as failed on the strength of it.
 */
const STATUS: Record<string, { label: string; tone: StatusTone }> = {
  generating: { label: "Generating", tone: "busy" },
  review: { label: "Pending review", tone: "waiting" },
  approved: { label: "Approved", tone: "positive" },
  rejected: { label: "Rejected", tone: "neutral" },
  failed: { label: "Failed", tone: "negative" },
};

/**
 * `metricool_post_id` outranks `status`, because pushing does not move it.
 *
 * Approve is queue movement only (round 1's D1), so a draft handed to Metricool
 * keeps whatever status it had — and every one of them so far was pushed
 * straight from `review`. Read live on 2026-08-16: fourteen drafts carry a post
 * id, five of them are `PUBLISHED` on Facebook, and all fourteen were rendering
 * a blue **Pending review** pill on this screen. The row menu had it right all
 * along — it disables everything and says "In Metricool" — but the badge is
 * what you read when you scan the column.
 *
 * "In Metricool" and not "Published", because the row cannot tell. A post id
 * means handed over, and the planner decides what became of it: seven of those
 * fourteen are still `draft=True` with a publication date three days past, and
 * will never go out. `PUBLISHED` / `Draft` / `Error` are the Schedule screen's
 * to say — it reads the planner, this screen reads a column.
 */
function StatusBadge({ draft }: { draft: Draft }) {
  const { label, tone } = draft.metricool_post_id
    ? { label: "In Metricool", tone: "positive" as const }
    : (STATUS[draft.status] ?? {
        label: draft.status,
        tone: "neutral" as const,
      });

  return <StatusPill tone={tone} label={label} />;
}

/** The hook is a paragraph; a row wants its first sentence. */
function title(draft: Draft): string {
  const source = draft.hook ?? draft.topic ?? "";
  if (!source) return "Untitled";
  const [first] = source.split(/(?<=[.!?])\s/);
  return (first ?? source).trim();
}
