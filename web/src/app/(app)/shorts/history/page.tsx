"use client";

import Link from "next/link";
import { useState } from "react";
import { Download, Play, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { ScreenHeader } from "@/components/screen";
import { QueryError } from "@/components/query-error";
import { StatusPill } from "@/components/status-pill";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Loading } from "@/components/loading";
import { deleteJob, downloadHref, listJobs, type YoutubeJob } from "@/lib/api/youtube";
import { emit } from "@/lib/store";
import { cn } from "@/lib/utils";
import { useQuery } from "@/lib/use-query";

/**
 * Everything this workspace has made, newest first.
 *
 * A table, not cards — the same call the Review queue makes (a table lines up
 * Status and Made so you scan down them). Completed rows offer the artifact;
 * everything else is a status and a reason.
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

  async function remove(job: YoutubeJob) {
    try {
      await deleteJob(job.id);
      emit();
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
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-left text-xs text-muted-foreground">
                <th className="px-4 py-2.5 font-medium">Video</th>
                <th className="px-4 py-2.5 font-medium">Status</th>
                <th className="px-4 py-2.5 font-medium">Trim</th>
                <th className="hidden px-4 py-2.5 font-medium md:table-cell">CTA</th>
                <th className="hidden px-4 py-2.5 font-medium md:table-cell">Made</th>
                <th className="px-4 py-2.5" />
              </tr>
            </thead>
            <tbody>
              {jobs.map((job) => (
                <tr
                  key={job.id}
                  className={cn(
                    "border-b last:border-0",
                    // A completed row is the artifact — the whole row opens and
                    // plays it, not just a button. Cursor + hover say so.
                    job.status === "completed" &&
                      "cursor-pointer hover:bg-muted/40",
                  )}
                  onClick={() =>
                    job.status === "completed" && setSelected(job)
                  }
                >
                  <td className="max-w-0 px-4 py-2.5">
                    <span className="block truncate font-medium">
                      {job.raw_title ?? `Short #${job.id}`}
                    </span>
                    <span className="block truncate font-mono text-[11px] text-muted-foreground">
                      {job.youtube_url ?? ""}
                    </span>
                  </td>
                  <td className="px-4 py-2.5">
                    <RowStatus job={job} />
                  </td>
                  <td className="px-4 py-2.5 tabular-nums text-muted-foreground">
                    {job.trim_duration}s
                  </td>
                  <td className="hidden px-4 py-2.5 text-muted-foreground md:table-cell">
                    {job.cta_title ?? "—"}
                  </td>
                  <td className="hidden px-4 py-2.5 text-muted-foreground md:table-cell">
                    {job.finished_at
                      ? new Date(job.finished_at).toLocaleDateString()
                      : "—"}
                  </td>
                  <td className="px-4 py-2.5 text-right">
                    {job.status === "completed" ? (
                      <div className="flex items-center justify-end gap-1">
                        <Button
                          variant="ghost"
                          size="icon"
                          aria-label="Play video"
                          onClick={(event) => {
                            event.stopPropagation();
                            setSelected(job);
                          }}
                        >
                          <Play className="size-4" />
                        </Button>
                        <Button asChild variant="ghost" size="icon" aria-label="Download mp4">
                          <a
                            href={downloadHref(job.id)}
                            download
                            onClick={(event) => event.stopPropagation()}
                          >
                            <Download className="size-4" />
                          </a>
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          aria-label="Remove"
                          onClick={() => void remove(job)}
                        >
                          <Trash2 className="size-4" />
                        </Button>
                      </div>
                    ) : (
                      <Button
                        variant="ghost"
                        size="icon"
                        aria-label="Remove"
                        onClick={() => void remove(job)}
                      >
                        <Trash2 className="size-4" />
                      </Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* The artifact, on demand: clicking a completed row opens the video in
          a dialog (the app's lightbox pattern), so history becomes the library
          of what was made — not a table of filenames. */}
      <VideoDialog job={selected} onClose={() => setSelected(null)} />
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
    return (
      <span className="flex flex-col items-start gap-1">
        <StatusPill tone="negative" label="Failed" />
        {job.error_message ? (
          <span className="max-w-64 truncate text-[11px] text-muted-foreground" title={job.error_message}>
            {job.error_message}
          </span>
        ) : null}
      </span>
    );
  }
  return <StatusPill tone="busy" label={job.status === "queued" ? "Queued" : `Processing ${job.progress}%`} />;
}