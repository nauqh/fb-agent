"use client";

import { useMemo, useState } from "react";
import { Clapperboard, Download, Loader2, Plus, UploadCloud } from "lucide-react";
import { toast } from "sonner";

import { ScreenHeader } from "@/components/screen";
import { StatusPill } from "@/components/status-pill";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  NativeSelect,
  NativeSelectOption,
} from "@/components/ui/native-select";
import {
  enqueueVideo,
  getJob,
  listCtaTemplates,
  uploadCtaTemplate,
  downloadHref,
  type YoutubeJob,
} from "@/lib/api/youtube";
import { emit } from "@/lib/store";
import { useQuery } from "@/lib/use-query";
import { QueryError } from "@/components/query-error";
import { Loading } from "@/components/loading";

/**
 * Produce — the Shorts tool's one screen.
 *
 * Paste a link, pick the CTA, make a video. The row *is* the job: enqueue
 * returns an id immediately, the worker fills it, and this screen polls until
 * the produced mp4 is ready to play and download. No publishing, no brands,
 * no scheduling — that is deliberately not here yet (see the Shorts nav).
 */
export default function ProduceScreen() {
  const [url, setUrl] = useState("");
  const [ctaId, setCtaId] = useState<string>("");
  const [trim, setTrim] = useState("3");
  const [making, setMaking] = useState(false);
  const [jobId, setJobId] = useState<number | null>(null);
  const [ctaDialogOpen, setCtaDialogOpen] = useState(false);

  const { data: templates, loading, error, refresh } = useQuery(listCtaTemplates, []);
  const hasTemplates = (templates?.length ?? 0) > 0;

  const hint = useMemo(() => describeSource(url), [url]);

  /**
   * A single video is one job; a channel URL would be N. v1 ships the single
   * path — the first returned id is the one this screen watches.
   */
  async function make() {
    if (!url.trim() || !ctaId || !hasTemplates) return;
    setMaking(true);
    try {
      const result = await enqueueVideo(url.trim(), Number(ctaId), Number(trim));
      // The worker may already have finished by the time the poll starts.
      setJobId(result.video_ids[0] ?? null);
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "Could not enqueue");
    } finally {
      setMaking(false);
    }
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <ScreenHeader
        title="Produce"
        hint="Paste a link, pick your CTA, make a video."
      />

      {/* The scrollable column: the job card lands below the form, and with a
          short document the whole screen must be able to scroll to it — the
          app layout's `<main>` is `overflow-hidden`, so a screen that does not
          scroll itself traps the video below the fold with no way down. */}
      <div className="min-h-0 flex-1 overflow-y-auto pr-1">
        <div className="mx-auto w-full max-w-2xl">
          <div className="rounded-2xl border bg-card p-6">
          <form
            className="flex flex-col gap-5"
            onSubmit={(event) => {
              event.preventDefault();
              void make();
            }}
          >
            <div className="flex flex-col gap-2">
              <Label htmlFor="shorts-url">YouTube link</Label>
              <Input
                id="shorts-url"
                value={url}
                onChange={(event) => setUrl(event.target.value)}
                placeholder="https://www.youtube.com/shorts/EM41yq0OUQ4"
                className="font-mono text-xs"
                autoComplete="off"
              />
              {/* Live parse hint: what the link is, before the operator commits. */}
              {hint ? (
                <p className="text-xs text-muted-foreground">{hint}</p>
              ) : null}
            </div>

            <div className="flex flex-col gap-2">
              <Label>CTA clip</Label>
              {loading ? (
                <div className="h-8 rounded-lg border bg-muted/50" />
              ) : error ? (
                <QueryError error={error} onRetry={refresh} />
              ) : !hasTemplates ? (
                <CtaEmptyState onOpen={() => setCtaDialogOpen(true)} />
              ) : (
                <div className="flex gap-2">
                  <NativeSelect
                    value={ctaId}
                    onValueChange={setCtaId}
                    ariaLabel="Choose a CTA clip"
                    className="flex-1"
                  >
                    <NativeSelectOption value="">Choose a clip</NativeSelectOption>
                    {templates!.map((template) => (
                      <NativeSelectOption key={template.id} value={String(template.id)}>
                        {template.title}
                      </NativeSelectOption>
                    ))}
                  </NativeSelect>
                  <Button
                    type="button"
                    variant="outline"
                    size="icon"
                    onClick={() => setCtaDialogOpen(true)}
                    aria-label="Add a CTA clip"
                  >
                    <Plus className="size-4" />
                  </Button>
                </div>
              )}
            </div>

            <div className="flex flex-col gap-2">
              <Label htmlFor="shorts-trim">Trim</Label>
              <div className="flex items-center gap-3">
                <NativeSelect
                  value={trim}
                  onValueChange={setTrim}
                  ariaLabel="Trim length"
                  className="w-28"
                >
                  {["1", "3", "5", "10", "15", "30", "60"].map((value) => (
                    <NativeSelectOption key={value} value={value}>
                      {value}s
                    </NativeSelectOption>
                  ))}
                </NativeSelect>
                <p className="text-xs text-muted-foreground">
                  Keeps the first N seconds, appends the CTA.
                </p>
              </div>
            </div>

            <div className="flex justify-end">
              <Button
                type="submit"
                disabled={making || !url.trim() || !ctaId || !hasTemplates}
              >
                {making ? (
                  <Loader2 className="size-4 animate-spin" />
                ) : (
                  <Clapperboard className="size-4" />
                )}
                Make video
              </Button>
            </div>
          </form>
        </div>

        {jobId !== null ? (
          <JobCard key={jobId} jobId={jobId} />
        ) : null}
        </div>
      </div>

      <CtaDialog
        open={ctaDialogOpen}
        onOpenChange={setCtaDialogOpen}
        onUploaded={() => {
          void refresh();
        }}
      />
    </div>
  );
}

/** The empty-strip onboarding: no clips yet, so the form cannot proceed. */
function CtaEmptyState({ onOpen }: { onOpen: () => void }) {
  return (
    <button
      type="button"
      onClick={onOpen}
      className="flex flex-col items-center gap-2 rounded-xl border border-dashed p-8 text-center text-sm text-muted-foreground transition-colors hover:bg-muted/40"
    >
      <UploadCloud className="size-5" />
      <span>
        No CTA clip yet. <span className="text-foreground">Add your first one</span> —
        it&rsquo;s the clip appended to every video.
      </span>
    </button>
  );
}

/**
 * The produced artifact. Polls while the row is in flight, then the mp4 is
 * the star: a real `<video>` plus the download link.
 */
function JobCard({ jobId }: { jobId: number }) {
  const { data: job, error, loading } = useQuery(
    () => getJob(jobId),
    [jobId],
    {
      intervalMs: 2_000,
      pollWhile: (job) =>
        job === null || job.status === "queued" || job.status === "processing",
    },
  );

  if (loading && !job) {
    return <div className="mt-4"><Loading label="Making your video" className="h-40" /></div>;
  }

  // The worker finished faster than the first poll beat? No — the query's
  // first attempt is awaited before data arrives. `!job` then means 404.
  if (error || !job) return null;

  const busy = job.status === "queued" || job.status === "processing";

  return (
    <div className="mt-4 rounded-2xl border bg-card p-6">
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate text-sm font-medium">
            {job.raw_title ?? `Short #${job.id}`}
          </p>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {job.cta_title ? `Made by ${job.cta_title}` : ""} · {job.trim_duration}s trim
          </p>
        </div>
        <JobStatus job={job} />
      </div>

      {busy ? (
        <div className="mt-4 h-1.5 w-full overflow-hidden rounded-full bg-muted">
          <div
            className="h-full rounded-full bg-gold transition-[width] duration-500 ease-linear"
            style={{ width: `${job.progress}%` }}
          />
        </div>
      ) : null}

      {!busy && job.status === "completed" ? (
        <div className="mt-4 flex flex-col gap-3">
          <video
            className="mx-auto max-h-96 rounded-xl border bg-black"
            controls
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

      {job.status === "failed" && job.error_message ? (
        <p className="mt-4 rounded-lg border border-red-600/25 bg-red-500/10 px-3 py-2 text-xs text-red-700 dark:text-red-400">
          {job.error_message}
        </p>
      ) : null}
    </div>
  );
}

function JobStatus({ job }: { job: YoutubeJob }) {
  if (job.status === "completed") {
    return <StatusPill tone="positive" label="Completed" />;
  }
  if (job.status === "failed") {
    return <StatusPill tone="negative" label="Failed" />;
  }
  return <StatusPill tone="busy" label={`Processing ${job.progress}%`} />;
}

/** The + clip dialog: a file and a name, one action. */
function CtaDialog({
  open,
  onOpenChange,
  onUploaded,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onUploaded: () => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [saving, setSaving] = useState(false);

  async function save() {
    if (!file || !title.trim()) return;
    setSaving(true);
    try {
      await uploadCtaTemplate(file, title.trim());
      emit();
      onUploaded();
      setFile(null);
      setTitle("");
      onOpenChange(false);
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "Upload failed");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogTitle>Add a CTA clip</DialogTitle>
        <DialogDescription>
          An mp4, appended to the end of every video you make. Keep it short.
        </DialogDescription>
        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <Label htmlFor="cta-title">Name</Label>
            <Input
              id="cta-title"
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              placeholder="Bible Focus"
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="cta-file">Clip</Label>
            <Input
              id="cta-file"
              type="file"
              accept="video/mp4"
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
            />
            <p className="text-xs text-muted-foreground">
              {file
                ? `${file.name} · ${(file.size / 1024 / 1024).toFixed(1)} MB`
                : "mp4 up to 50 MB."}
            </p>
          </div>
        </div>
        <DialogFooter>
          <Button
            onClick={() => void save()}
            disabled={saving || !file || !title.trim()}
          >
            {saving ? <Loader2 className="size-4 animate-spin" /> : <UploadCloud className="size-4" />}
            Add clip
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** The URL shapes the backend accepts, mirrored for a live hint. Mirrors
 *  `parse_youtube_source` in api/app/youtube/sources.py — drift here is a
 *  hint that disagrees with the button, never a wrong acceptance. */
function describeSource(url: string): string | null {
  const trimmed = url.trim();
  if (!trimmed) return null;

  const single = /^https?:\/\/(?:www\.|m\.)?(?:youtube\.com\/(?:watch\?v=|shorts\/|embed\/)|youtu\.be\/)[\w-]{11}(?:[?#&].*)?$/i;
  const channel = /^https?:\/\/(?:www\.|m\.)?youtube\.com\/@[^/?#]+(?:[?#].*)?$/i;

  if (single.test(trimmed) && /\/shorts\//i.test(trimmed)) {
    return "Short — download and process this video.";
  }
  if (single.test(trimmed)) {
    return "Video — download and process this video.";
  }
  if (channel.test(trimmed)) {
    return "Channel Shorts — pick one in the next version.";
  }
  return "Invalid URL. Supported: /shorts/ID, watch?v=..., youtu.be/..., @channel/shorts.";
}