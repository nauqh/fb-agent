"use client";

import { useState } from "react";
import { BarChart3, Bookmark, BookmarkCheck, ExternalLink, Loader2 } from "lucide-react";
import { toast } from "sonner";

import { QueryError } from "@/components/query-error";
import { ScreenHeader } from "@/components/screen";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  getPerformance,
  listSaved,
  savePost,
  unsavePost,
  type PostStats,
  type SavedPost,
} from "@/lib/api/overview";
import { fullDate, metric } from "@/lib/format";
import { usePageScope } from "@/lib/page-scope";
import { useQuery } from "@/lib/use-query";
import { cn } from "@/lib/utils";

/**
 * How the Page's published posts did, and the ones worth keeping.
 *
 * The client asked for both together — "see post performance there and save the
 * top-performing posts for future reference/reuse" — and they are two tabs
 * rather than two screens because the second is made entirely out of the first.
 *
 * **Performance is read live and stored nowhere.** Metricool's numbers move
 * every day as Facebook's counts catch up, so a cached copy is a wrong copy —
 * the same reasoning the Schedule screen follows for the planner. The saved
 * half is the opposite and needs a row, because their stats call takes a date
 * range: an old post appears in no read at all.
 */
export default function OverviewScreen() {
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <ScreenHeader
        title="Overview"
        hint="How this Page's posts did, and the ones worth keeping."
      />

      <Tabs defaultValue="performance" className="flex min-h-0 flex-1 flex-col gap-4">
        <TabsList className="shrink-0 gap-1.5 p-1 *:min-w-32 *:px-4">
          <TabsTrigger value="performance">Performance</TabsTrigger>
          <TabsTrigger value="saved">Saved</TabsTrigger>
        </TabsList>

        <TabsContent value="performance" className="min-h-0 flex-1 overflow-y-auto pr-3">
          <Performance />
        </TabsContent>
        <TabsContent value="saved" className="min-h-0 flex-1 overflow-y-auto pr-3">
          <Saved />
        </TabsContent>
      </Tabs>
    </div>
  );
}

/**
 * Published posts, best first.
 *
 * The sort is the server's. Metricool accepts a `sortcolumn` and does not
 * honour it — asking for reactions returned a zero-reaction post first while
 * the same window held one with 160,282 — so ordering by their response would
 * be arbitrary.
 */
function Performance() {
  const { pageId } = usePageScope();
  const [days, setDays] = useState(90);
  const [busy, setBusy] = useState<string | null>(null);

  const { data, error, loading, refresh } = useQuery(
    () => getPerformance(pageId!, days),
    [pageId, days],
    { enabled: pageId !== null },
  );

  async function keep(post: PostStats) {
    if (pageId === null) return;
    setBusy(post.post_id);
    try {
      await savePost(pageId, post);
      await refresh();
      toast.success("Saved for reference.");
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "Could not save that post");
    } finally {
      setBusy(null);
    }
  }

  if (error) return <QueryError error={error} onRetry={refresh} />;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <p className="text-xs text-muted-foreground">
          Read live from Metricool, best first. Their figures lag Facebook by a
          day or so, so the newest posts legitimately read as zero.
        </p>
        {/* 30 is offered but is not the default: over that window most of the
            response is posts whose counts have not landed yet, and the screen
            reads as a Page that stopped posting. */}
        <div className="flex shrink-0 gap-1">
          {[30, 90, 180].map((option) => (
            <button
              key={option}
              type="button"
              onClick={() => setDays(option)}
              className={cn(
                "rounded-md border px-2 py-1 text-xs transition-colors",
                option === days
                  ? "border-primary bg-primary/10 text-primary"
                  : "text-muted-foreground hover:bg-muted",
              )}
            >
              {option}d
            </button>
          ))}
        </div>
      </div>

      {loading || !data ? (
        <div className="space-y-2">
          {Array.from({ length: 6 }).map((_, index) => (
            <Skeleton key={index} className="h-20 rounded-lg" />
          ))}
        </div>
      ) : data.length === 0 ? (
        <p className="rounded-lg border border-dashed p-10 text-center text-sm text-muted-foreground">
          Nothing published in this window.
        </p>
      ) : (
        <div className="space-y-2">
          {data.map((post) => (
            <PostRow
              key={post.post_id}
              post={post}
              busy={busy === post.post_id}
              onSave={() => void keep(post)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

/** One published post and its numbers. */
function PostRow({
  post,
  busy,
  onSave,
}: {
  post: PostStats;
  busy: boolean;
  onSave: () => void;
}) {
  return (
    <div className="group flex items-start gap-3 rounded-lg border p-3 transition-colors hover:bg-muted/40">
      <Thumbnail src={post.picture_url} />

      <div className="min-w-0 flex-1">
        <p className="line-clamp-2 text-sm">{post.text || "(no text)"}</p>
        <p className="pt-1 text-[11px] text-muted-foreground">
          {fullDate(post.published_at)}
          {post.permalink_url ? (
            <a
              href={post.permalink_url}
              target="_blank"
              rel="noreferrer"
              className="ml-2 inline-flex items-center gap-1 hover:underline"
            >
              open <ExternalLink className="size-3" />
            </a>
          ) : null}
        </p>
      </div>

      <div className="flex shrink-0 items-center gap-4 text-xs tabular-nums">
        <Metric label="reactions" value={post.reactions} />
        <Metric label="comments" value={post.comments} />
        <Metric label="shares" value={post.shares} />
        <Metric label="reach" value={post.impressions} />
      </div>

      <button
        type="button"
        onClick={onSave}
        disabled={busy || post.saved}
        aria-label={post.saved ? "Already saved" : "Save this post"}
        title={post.saved ? "Already saved" : "Keep this post for reference"}
        className="shrink-0 rounded p-1.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground disabled:opacity-60"
      >
        {busy ? (
          <Loader2 className="size-4 animate-spin" />
        ) : post.saved ? (
          <BookmarkCheck className="size-4 text-primary" />
        ) : (
          <Bookmark className="size-4" />
        )}
      </button>
    </div>
  );
}

/**
 * The post's picture, or a stand-in.
 *
 * Facebook's CDN URLs are signed and expire — the same trap the competitor
 * pictures document — so a missing thumbnail is the expected end state rather
 * than a fault. The row carries its numbers either way.
 */
function Thumbnail({ src }: { src: string | null }) {
  if (!src) {
    return (
      <div className="flex size-16 shrink-0 items-center justify-center rounded-md border bg-muted">
        <BarChart3 className="size-4 text-muted-foreground/50" />
      </div>
    );
  }
  // A Facebook CDN URL, not in `next.config.ts`'s image hosts, and expected to
  // expire — `next/image` can do nothing useful with either fact.
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img src={src} alt="" className="size-16 shrink-0 rounded-md border object-cover" />
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <span className="w-16 text-right">
      <span className="block font-medium">{metric(value)}</span>
      <span className="block text-[10px] text-muted-foreground">{label}</span>
    </span>
  );
}

/** The kept posts. Their numbers are a snapshot, not a live figure. */
function Saved() {
  const { pageId } = usePageScope();
  const { data, error, loading, refresh } = useQuery(
    () => listSaved(pageId!),
    [pageId],
    { enabled: pageId !== null },
  );

  async function drop(saved: SavedPost) {
    try {
      await unsavePost(saved.id);
      await refresh();
      toast.success("Removed.");
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "Could not remove");
    }
  }

  if (error) return <QueryError error={error} onRetry={refresh} />;
  if (loading || !data) return <Skeleton className="h-40 rounded-lg" />;

  if (data.length === 0) {
    return (
      <p className="rounded-lg border border-dashed p-10 text-center text-sm text-muted-foreground">
        Nothing saved yet. Keep a post from the Performance tab and it stays
        here — including after it drops out of the reporting window.
      </p>
    );
  }

  return (
    <div className="space-y-2">
      <p className="text-xs text-muted-foreground">
        The numbers below are what each post had scored when it was saved, not a
        live figure.
      </p>
      {data.map((saved) => (
        <div
          key={saved.id}
          className="group flex items-start gap-3 rounded-lg border p-3 transition-colors hover:bg-muted/40"
        >
          <Thumbnail src={saved.picture_url} />
          <div className="min-w-0 flex-1">
            <p className="line-clamp-2 text-sm">{saved.text || "(no text)"}</p>
            <p className="pt-1 text-[11px] tabular-nums text-muted-foreground">
              {metric(saved.reactions)} reactions · {metric(saved.comments)} comments
              · {metric(saved.shares)} shares
              {saved.permalink_url ? (
                <a
                  href={saved.permalink_url}
                  target="_blank"
                  rel="noreferrer"
                  className="ml-2 inline-flex items-center gap-1 hover:underline"
                >
                  open <ExternalLink className="size-3" />
                </a>
              ) : null}
            </p>
          </div>
          <button
            type="button"
            onClick={() => void drop(saved)}
            aria-label="Remove from saved"
            title="Stop keeping this post"
            className="shrink-0 rounded p-1.5 text-muted-foreground opacity-0 transition-opacity hover:bg-destructive/10 hover:text-destructive group-hover:opacity-100 focus-visible:opacity-100"
          >
            <BookmarkCheck className="size-4" />
          </button>
        </div>
      ))}
    </div>
  );
}
