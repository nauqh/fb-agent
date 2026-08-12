"use client";

import { useState } from "react";
import {
  BarChart3,
  Bookmark,
  BookmarkCheck,
  ExternalLink,
  Loader2,
  Sparkles,
} from "lucide-react";
import { toast } from "sonner";

import { QueryError } from "@/components/query-error";
import { Button } from "@/components/ui/button";
import { ScreenHeader } from "@/components/screen";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  getPerformance,
  listSaved,
  savePost,
  reuseSaved,
  unsavePost,
  type PostStats,
  type SavedPost,
} from "@/lib/api/overview";
import { fullDate, metric } from "@/lib/format";
import { useRouter } from "next/navigation";

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
  const [days, setDays] = useState(30);
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
          Read live from Metricool, best first. The newest posts can still be
          catching up — their figures lag Facebook by about a day.
        </p>
        {/* 7 / 30 / 60, and 30 by default. An earlier version defaulted to 90
            on the theory that Metricool's lag made shorter windows read as a
            dead Page — measured against History Retraced, that is false: even
            over 7 days only 1 post of 28 has no reactions yet, and over 30 it
            is 1 of 219. 90 days is 657 rows, which is a scroll rather than an
            overview. */}
        <div className="flex shrink-0 gap-1">
          {[7, 30, 60].map((option) => (
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
        <div className="space-y-4">
          <Skeleton className="h-24 rounded-xl" />
          {Array.from({ length: 5 }).map((_, index) => (
            <Skeleton key={index} className="h-28 rounded-xl" />
          ))}
        </div>
      ) : data.length === 0 ? (
        <p className="rounded-lg border border-dashed p-10 text-center text-sm text-muted-foreground">
          Nothing published in this window.
        </p>
      ) : (
        <>
          <Totals posts={data} days={days} />
          <div className="space-y-2">
            {data.map((post, index) => (
              <PostRow
                key={post.post_id}
                post={post}
                rank={index + 1}
                // The best post in the window sets the bar's full width, so the
                // scale is "against the best of these" rather than an absolute
                // nobody has a feel for.
                best={data[0].engagement}
                busy={busy === post.post_id}
                onSave={() => void keep(post)}
              />
            ))}
          </div>
        </>
      )}
    </div>
  );
}

/**
 * What the window adds up to, above the list.
 *
 * An Overview should open with the numbers rather than with row one of 657.
 * Four tiles and no hero figure: these are four measures of equal standing, and
 * a hero is the *one* number a view leads with — picking one here would be
 * arbitrary.
 *
 * Values use the font's proportional figures, not `tabular-nums`. Tabular gives
 * every digit the width of a `0`, which reads loose at display sizes; it is for
 * columns that must align vertically, which is what the rows below are.
 */
function Totals({ posts, days }: { posts: PostStats[]; days: number }) {
  const reach = posts.reduce((sum, post) => sum + post.impressions, 0);
  const engagement = posts.reduce((sum, post) => sum + post.engagement, 0);

  return (
    <div className="grid grid-cols-2 gap-px overflow-hidden rounded-xl border bg-border sm:grid-cols-4">
      <Tile label="Posts" value={metric(posts.length)} note={`last ${days} days`} />
      <Tile label="Total reach" value={metric(reach)} note="impressions" />
      <Tile label="Total engagement" value={metric(engagement)} note="reactions + comments + shares" />
      <Tile label="Best post" value={metric(posts[0].engagement)} note="engagement" />
    </div>
  );
}

/** One stat tile: label in sentence case, value semibold and auto-compacted. */
function Tile({ label, value, note }: { label: string; value: string; note: string }) {
  return (
    <div className="bg-card px-4 py-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="pt-0.5 text-2xl font-semibold tracking-tight">{value}</p>
      <p className="text-[11px] text-muted-foreground">{note}</p>
    </div>
  );
}

/**
 * One published post and its numbers.
 *
 * The engagement bar is the only mark on the screen and it encodes magnitude,
 * so it is a single hue at one step, recessive, against the best post in the
 * window. Its job is to make "how far behind is row 40" answerable without
 * reading four figures — the numbers are still there for the exact answer.
 */
function PostRow({
  post,
  rank,
  best,
  busy,
  onSave,
}: {
  post: PostStats;
  rank: number;
  best: number;
  busy: boolean;
  onSave: () => void;
}) {
  const share = best > 0 ? Math.max(0.01, post.engagement / best) : 0;

  return (
    <div className="group flex items-stretch gap-4 rounded-xl border bg-card p-4 transition-colors hover:bg-muted/30">
      {/* Rank, not a bullet: the list is sorted, so its position is information.
          Muted — it names the row, it is not a measure. */}
      <span className="w-6 shrink-0 pt-1 text-right text-xs tabular-nums text-muted-foreground">
        {rank}
      </span>

      <Thumbnail src={post.picture_url} />

      <div className="flex min-w-0 flex-1 flex-col justify-between gap-2">
        <div className="min-w-0">
          <p className="line-clamp-2 text-sm leading-relaxed">
            {post.text || "(no text)"}
          </p>
          <p className="pt-1.5 text-[11px] text-muted-foreground">
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

        {/* 4px rounded end, anchored at the left. Sized against the best post
            in the window rather than an absolute nobody has a feel for. */}
        <div className="h-1 w-full max-w-md overflow-hidden rounded-full bg-muted">
          <div
            className="h-full rounded-full bg-foreground/30"
            style={{ width: `${share * 100}%` }}
          />
        </div>
      </div>

      {/* A column of numbers that must line up down the list, which is exactly
          what `tabular-nums` is for. */}
      <div className="flex shrink-0 items-start gap-5 tabular-nums">
        <Metric label="engagement" value={post.engagement} strong />
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
        className="h-fit shrink-0 rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground disabled:opacity-60"
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
      <div className="flex aspect-square w-20 shrink-0 items-center justify-center rounded-lg border bg-muted">
        <BarChart3 className="size-5 text-muted-foreground/50" />
      </div>
    );
  }
  // A Facebook CDN URL, not in `next.config.ts`'s image hosts, and expected to
  // expire — `next/image` can do nothing useful with either fact.
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={src}
      alt=""
      className="aspect-square w-20 shrink-0 rounded-lg border object-cover"
    />
  );
}

/**
 * One number in the row's column.
 *
 * `strong` marks engagement, which is the value the list is sorted by — the
 * others are its parts. Weight rather than colour: colour here would be
 * identity, and there is only one series.
 */
function Metric({
  label,
  value,
  strong,
}: {
  label: string;
  value: number;
  strong?: boolean;
}) {
  return (
    <span className="w-14 text-right">
      <span
        className={cn(
          "block text-sm",
          strong ? "font-semibold" : "font-medium text-muted-foreground",
        )}
      >
        {metric(value)}
      </span>
      <span className="block pt-0.5 text-[10px] text-muted-foreground">{label}</span>
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

  const router = useRouter();
  const [busy, setBusy] = useState<number | null>(null);

  /**
   * Write this one again. The saved post stays — reuse is not a move, and the
   * reference is the thing being kept.
   */
  async function reuse(saved: SavedPost) {
    setBusy(saved.id);
    try {
      const ids = await reuseSaved(saved.id);
      toast.success("Writing it again.", {
        description: `${ids.length} draft${ids.length === 1 ? "" : "s"} generating.`,
      });
      router.push("/review");
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "Could not reuse that post");
    } finally {
      setBusy(null);
    }
  }

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
          <div className="flex shrink-0 items-start gap-1">
            <Button
              variant="outline"
              size="sm"
              disabled={busy === saved.id}
              onClick={() => void reuse(saved)}
              title="Write this story again — a fresh hook, caption, first comment and image."
            >
              {busy === saved.id ? (
                <Loader2 className="size-3.5 animate-spin" />
              ) : (
                <Sparkles className="size-3.5" />
              )}
              Write again
            </Button>
            <button
              type="button"
              onClick={() => void drop(saved)}
              aria-label="Remove from saved"
              title="Stop keeping this post"
              className="rounded p-1.5 text-muted-foreground opacity-0 transition-opacity hover:bg-destructive/10 hover:text-destructive group-hover:opacity-100 focus-visible:opacity-100"
            >
              <BookmarkCheck className="size-4" />
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}
