"use client";

import Link from "next/link";
import { useState } from "react";
import { Download, ExternalLink, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { ScreenHeader } from "@/components/screen";
import { QueryError } from "@/components/query-error";
import { StatusPill } from "@/components/status-pill";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogTitle,
} from "@/components/ui/dialog";
import { Loading } from "@/components/loading";
import { deleteJob, downloadHref, listJobs, type YoutubeJob } from "@/lib/api/youtube";
import { emit } from "@/lib/store";
import { fullDate, timeAgo } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useQuery } from "@/lib/use-query";

/**
 * Everything this workspace has made, newest first.
 *
 * A list, not a table — the columns fought each other for width and the two
 * pieces of text that matter when a job goes wrong (the source URL and the
 * error) kept losing, truncated to slivers. Each row is now three stacked
 * lines: what it is and how it landed, where it came from, and — for a failed
 * job — the whole reason why, wrapped, in the only red on the screen.
 * Completed rows offer the artifact; everything else is a status and a reason.
 */
export default function HistoryScreen() {
  const { data: jobs, loading, error, refresh } = useQuery(
    () => listJobs(50),
    [],
    {
      // While anything is in flight the rows can move; once everything is
      // settled a refresh is the only way it changes again.
      intervalMs: 4_000,
      pollWhile: (rows) =>
        rows === null ||
        rows.some(
          (job) => job.status === "queued" || job.status === "processing",
        ),
    },
  );

  const [selected, setSelected] = useState<YoutubeJob | null>(null);

  // Delete asks first — the produced mp4 goes with the row and there is no
  // way back (the review queue's rule: reject is undoable, delete is not).
  const [pendingDelete, setPendingDelete] = useState<YoutubeJob | null>(null);

  async function remove(job: YoutubeJob) {
    try {
      await deleteJob(job.id);
      emit();
      setPendingDelete(null);
      await refresh();
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "Could not remove");
    }
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <ScreenHeader title="History" hint="Everything Shorts has made." />

      {error ? (
        <QueryError error={error} onRetry={refresh} />
      ) : loading || !jobs ? (
        <Loading label="Loading history" className="h-64" />
      ) : jobs.length === 0 ? (
        <p className="rounded-2xl border border-dashed p-10 text-center text-sm text-muted-foreground">
          Nothing made yet. Paste a link on{" "}
          <Link href="/shorts" className="underline underline-offset-2">
            Produce
          </Link>
          .
        </p>
      ) : (
        <div className="min-h-0 flex-1 overflow-y-auto rounded-2xl border bg-card">
          <div className="divide-y">
            {jobs.map((job) => (
              <JobRow
                key={job.id}
                job={job}
                onPlay={() => setSelected(job)}
                onRemove={() => setPendingDelete(job)}
              />
            ))}
          </div>
        </div>
      )}

      {/* The artifact, on demand: clicking a completed row opens the video in
          a dialog (the app's lightbox pattern), so history becomes the library
          of what was made — not a table of filenames. */}
      <VideoDialog job={selected} onClose={() => setSelected(null)} />

      <Dialog
        open={pendingDelete !== null}
        onOpenChange={(open) => !open && setPendingDelete(null)}
      >
        <DialogContent className="sm:max-w-md">
          <DialogTitle>
            Delete “{pendingDelete?.raw_title ?? `Short #${pendingDelete?.id}`}”?
          </DialogTitle>
          <DialogDescription>
            The produced file is removed with the row. There is no way back —
            make it again on Produce if you need it.
          </DialogDescription>
          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => setPendingDelete(null)}>
              Keep
            </Button>
            <Button
              variant="destructive"
              onClick={() => pendingDelete && void remove(pendingDelete)}
            >
              <Trash2 className="size-4" />
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

/**
 * One job, three lines:
 *
 * 1. **Title · status · made · actions** — the scan line. The title opens the
 *    video when there is one, so the play affordance lives where the eye
 *    already is.
 * 2. **Source URL · trim · CTA** — the recipe, in mono. The URL is a real
 *    link out to YouTube, truncated but titled in full.
 * 3. **The error, for a failed job** — never truncated. It is the only
 *    record of why the job died.
 */
function JobRow({
  job,
  onPlay,
  onRemove,
}: {
  job: YoutubeJob;
  onPlay: () => void;
  onRemove: () => void;
}) {
  const done = job.status === "completed";

  return (
    <div
      className={cn(
        "flex flex-col gap-2 px-4 py-3.5 transition-colors duration-100",
        done && "hover:bg-muted/40 active:bg-muted/70",
      )}
    >
      <div className="flex items-center gap-3">
        {/* The title is the row's action when the artifact exists. */}
        {done ? (
          <button
            type="button"
            onClick={onPlay}
            className="min-w-0 flex-1 truncate text-left text-sm font-medium outline-none focus-visible:ring-ring/50 focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-offset-card"
            title={`Play ${job.raw_title ?? `Short #${job.id}`}`}
          >
            {job.raw_title ?? `Short #${job.id}`}
          </button>
        ) : (
          <span className="min-w-0 flex-1 truncate text-sm font-medium">
            {job.raw_title ?? `Short #${job.id}`}
          </span>
        )}

        <div className="w-40 shrink-0">
          <RowStatus job={job} />
        </div>

        <span
          className="hidden w-20 shrink-0 text-right font-mono text-[11px] text-muted-foreground sm:block"
          title={job.finished_at ? fullDate(job.finished_at) : undefined}
        >
          {job.finished_at ? timeAgo(job.finished_at) : "—"}
        </span>

        <div className="flex shrink-0 items-center gap-1">
          {done ? (
            <Button asChild variant="ghost" size="icon" aria-label="Download mp4">
              <a href={downloadHref(job.id)} download>
                <Download className="size-4" />
              </a>
            </Button>
          ) : null}
          <Button variant="ghost" size="icon" aria-label="Remove" onClick={onRemove}>
            <Trash2 className="size-4" />
          </Button>
        </div>
      </div>

      <div className="flex items-center gap-2 pl-0.5 font-mono text-[11px] text-muted-foreground">
        {job.youtube_url ? (
          <a
            href={job.youtube_url}
            target="_blank"
            rel="noreferrer"
            className="flex min-w-0 items-center gap-1 hover:text-foreground hover:underline hover:underline-offset-2"
            title={job.youtube_url}
          >
            <ExternalLink className="size-3 shrink-0" />
            <span className="truncate">{job.youtube_url}</span>
          </a>
        ) : null}
        <span aria-hidden className="shrink-0">·</span>
        <span className="shrink-0 tabular-nums">{job.trim_duration}s</span>
        <span aria-hidden className="shrink-0">·</span>
        <span className="truncate" title={job.cta_title ?? undefined}>
          {job.cta_title ?? "no CTA"}
        </span>
      </div>

      {job.status === "failed" && job.error_message ? (
        <p className="break-words rounded-lg border border-destructive/20 bg-destructive/5 px-3 py-2 text-xs leading-relaxed text-destructive dark:text-destructive/90">
          {job.error_message}
        </p>
      ) : null}
    </div>
  );
}

function VideoDialog({ job, onClose }: { job: YoutubeJob | null; onClose: () => void }) {
  return (
    <Dialog open={job !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogTitle>{job?.raw_title ?? "Produced video"}</DialogTitle>
        <DialogDescription className="sr-only">
          The video this job produced, with download.
        </DialogDescription>
        {job && job.status === "completed" ? (
          <div className="flex flex-col gap-3">
            <video
              className="max-h-[70vh] w-full rounded-lg border bg-black"
              controls
              autoPlay
              playsInline
              preload="metadata"
              src={downloadHref(job.id)}
            />
            <div className="flex justify-center">
              <Button asChild variant="outline">
                <a href={downloadHref(job.id)} download>
                  <Download className="size-4" />
                  Download mp4
                </a>
              </Button>
            </div>
          </div>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}

function RowStatus({ job }: { job: YoutubeJob }) {
  if (job.status === "completed") {
    return <StatusPill tone="positive" label="Done" />;
  }
  if (job.status === "failed") {
    return <StatusPill tone="negative" label="Failed" />;
  }
  return <StatusPill tone="busy" label={job.status === "queued" ? "Queued" : `Processing ${job.progress}%`} />;
}
