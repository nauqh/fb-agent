"use client";

import { useState } from "react";
import {
  BarChart3,
  Bookmark,
  BookmarkCheck,
  ExternalLink,
  Loader2,
  Repeat2,
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
  repostSaved,
  reuseSaved,
  unsavePost,
  type PostStats,
  type SavedPost,
} from "@/lib/api/overview";
import { fullDate, metric, timeAgo } from "@/lib/format";
import { useRouter } from "next/navigation";

import { usePageScope } from "@/lib/page-scope";
import { useQuery } from "@/lib/use-query";

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
            overview.

            The shared pill, like every other choice-between-alternatives in the
            app. It was a row of bordered boxes with a `bg-primary/10` active
            state — a near-white tint barely distinguishable from the inactive
            ones. */}
        <Tabs value={String(days)} onValueChange={(next) => setDays(Number(next))}>
          <TabsList className="w-fit shrink-0">
            {[7, 30, 60].map((option) => (
              <TabsTrigger key={option} value={String(option)}>
                {option}d
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
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
          <div className="rounded-lg border bg-card px-2">
            {data.map((post, index) => (
              <PostRow
                key={post.post_id}
                post={post}
                rank={index + 1}
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
    <div className="grid grid-cols-2 gap-px overflow-hidden rounded-lg border bg-border sm:grid-cols-4">
      <Tile index="01" label="Posts" value={metric(posts.length)} note={`last ${days} days`} />
      <Tile index="02" label="Total reach" value={metric(reach)} note="impressions" />
      <Tile index="03" label="Engagement" value={metric(engagement)} note="reactions + comments + shares" />
      <Tile index="04" label="Best post" value={metric(posts[0].engagement)} note="engagement" />
    </div>
  );
}

/**
 * One stat tile.
 *
 * Label and index in mono uppercase at the top, value large at the bottom —
 * the shape the reference designs use for a panel, and the reason it works
 * here is that four tiles then read as one instrument rather than four boxes.
 * Mono is doing real work: it marks everything that is *metadata* (the label,
 * the index, the note) so the only thing set in the body face is the number.
 */
function Tile({
  index,
  label,
  value,
  note,
}: {
  index: string;
  label: string;
  value: string;
  note: string;
}) {
  return (
    <div className="flex min-h-28 flex-col justify-between bg-card px-4 py-3">
      <div className="flex items-baseline justify-between gap-2">
        <p className="font-mono text-[11px] tracking-[0.12em] text-muted-foreground uppercase">
          {label}
        </p>
        <p className="font-mono text-[11px] text-muted-foreground/70">{index}</p>
      </div>
      <div>
        {/* Proportional figures, not `tabular-nums`: tabular gives every digit
            the width of a `0`, which reads loose at display sizes. It is for
            columns that must align vertically, which is what the rows are. */}
        <p className="text-2xl font-semibold tracking-tight">{value}</p>
        <p className="pt-0.5 font-mono text-[11px] text-muted-foreground">{note}</p>
      </div>
    </div>
  );
}

/**
 * One published post and its numbers.
 *
 * **Rebuilt 2026-08-18 because the screen was unreadable.** Every row was a
 * bordered card carrying two lines of caption, five labelled metrics, a
 * progress bar, a date, a rank and a bookmark — about eighteen elements, six
 * rows deep, and the caption is the loudest thing on a screen nobody comes to
 * for captions. Measured against the reference designs, the fix is subtraction:
 *
 * - the caption is an **identifier**, so it gets one line and stops
 * - the four secondary metrics drop to one mono line, which is how a spec sheet
 *   carries numbers you scan rather than compare
 * - **engagement stays large and right-aligned** — it is what the list is
 *   sorted by, so it is the one figure that earns size
 * - the bar is gone. It encoded the same thing the sorted order already says,
 *   and it was the element that made a list of forty rows feel like a chart
 * - cards become **rows on hairlines**: forty bordered boxes is forty frames
 *   competing with the content inside them
 */
function PostRow({
  post,
  rank,
  busy,
  onSave,
}: {
  post: PostStats;
  rank: number;
  busy: boolean;
  onSave: () => void;
}) {
  return (
    <div className="group flex items-center gap-4 border-b px-2 py-3 transition-colors last:border-0 hover:bg-muted/40">
      {/* Rank, not a bullet: the list is sorted, so its position is
          information. Mono and muted — it names the row, it is not a measure. */}
      <span className="w-6 shrink-0 text-right font-mono text-[11px] text-muted-foreground">
        {rank}
      </span>

      <Thumbnail src={post.picture_url} />

      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium">{post.text || "(no text)"}</p>
        <p className="flex flex-wrap items-center gap-x-2 pt-1 font-mono text-[11px] text-muted-foreground">
          <span>{metric(post.reactions)} reactions</span>
          <span aria-hidden>·</span>
          <span>{metric(post.comments)} comments</span>
          <span aria-hidden>·</span>
          <span>{metric(post.shares)} shares</span>
          <span aria-hidden>·</span>
          <span>{metric(post.impressions)} reach</span>
        </p>
      </div>

      {/* The figure the list is ordered by, and the date. `tabular-nums` here
          and not on the tiles: this is a column that has to align down forty
          rows, which is the one thing tabular figures are for. */}
      <div className="shrink-0 text-right">
        <p className="text-base font-semibold tabular-nums">
          {metric(post.engagement)}
        </p>
        <p className="font-mono text-[11px] text-muted-foreground">
          {timeAgo(post.published_at)}
        </p>
      </div>

      <div className="flex w-16 shrink-0 items-center justify-end gap-0.5">
        {post.permalink_url ? (
          <a
            href={post.permalink_url}
            target="_blank"
            rel="noreferrer"
            title="Open on Facebook"
            className="rounded p-1.5 text-muted-foreground opacity-0 transition-opacity hover:text-foreground group-hover:opacity-100 focus-visible:opacity-100"
          >
            <ExternalLink className="size-3.5" />
          </a>
        ) : null}
        <button
          type="button"
          onClick={onSave}
          disabled={busy || post.saved}
          aria-label={post.saved ? "Already saved" : "Save this post"}
          title={post.saved ? "Already saved" : "Keep this post for reference"}
          className="rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground disabled:opacity-60"
        >
          {busy ? (
            <Loader2 className="size-4 animate-spin" />
          ) : post.saved ? (
            <BookmarkCheck className="size-4 text-foreground" />
          ) : (
            <Bookmark className="size-4" />
          )}
        </button>
      </div>
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
 * `Metric` used to live here: one labelled figure, repeated five times per row.
 *
 * It is gone with the row rebuild above. Five stacked label/value pairs per row
 * meant ten text elements carrying five numbers, and at forty rows that was the
 * bulk of what made the screen unreadable. The four secondary figures are now
 * one mono line, and engagement — the only one the sort depends on — is the
 * figure that gets size.
 */

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

  /**
   * Put the original back in the queue — same caption, same picture.
   *
   * It lands at `review` rather than going straight out, which is the whole
   * shape of the feature: publishing is its own decision everywhere else in
   * this app, and a repost is the one case where the picture may have expired
   * off Facebook's CDN since it was saved. The API copies the image into our
   * bucket first and refuses with a readable sentence when it cannot.
   */
  async function repost(saved: SavedPost) {
    setBusy(saved.id);
    try {
      const draft = await repostSaved(saved.id);
      toast.success("Queued the original.", {
        description: "Publish it from Review — nothing has gone out yet.",
        action: { label: "Review", onClick: () => router.push(`/review?draft=${draft.id}`) },
      });
    } catch (cause) {
      // The 409 for an expired image names what happened and what to do
      // instead, so it is shown as written rather than replaced.
      toast.error(cause instanceof Error ? cause.message : "Could not repost that");
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
    <div className="space-y-3">
      <p className="text-xs text-muted-foreground">
        The numbers below are what each post had scored when it was saved, not a
        live figure. <strong className="font-medium text-foreground">Repost</strong>{" "}
        queues the original caption and picture; <strong className="font-medium text-foreground">Write again</strong>{" "}
        sends the story back through the writer for a fresh one.
      </p>

      <div className="rounded-lg border bg-card px-2">
        {data.map((saved) => (
          <div
            key={saved.id}
            className="group flex items-center gap-4 border-b px-2 py-3 transition-colors last:border-0 hover:bg-muted/40"
          >
            <Thumbnail src={saved.picture_url} />

            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium">
                {saved.text || "(no text)"}
              </p>
              <p className="flex flex-wrap items-center gap-x-2 pt-1 font-mono text-[11px] text-muted-foreground">
                <span>{metric(saved.reactions)} reactions</span>
                <span aria-hidden>·</span>
                <span>{metric(saved.comments)} comments</span>
                <span aria-hidden>·</span>
                <span>{metric(saved.shares)} shares</span>
              </p>
            </div>

            {/* The client's ask: "there needs to be a visible date showing how
                many days ago it was posted last." Relative, because that is the
                question — whether it is far enough back to run again — and the
                exact stamp is a hover away rather than a second line nobody
                reads. */}
            <div className="hidden shrink-0 text-right sm:block">
              <p className="text-sm font-medium" title={fullDate(saved.published_at)}>
                {timeAgo(saved.published_at)}
              </p>
              <p className="font-mono text-[11px] text-muted-foreground">
                last posted
              </p>
            </div>

            <div className="flex shrink-0 items-center gap-1">
              <Button
                variant="outline"
                size="sm"
                className="h-7"
                disabled={busy === saved.id}
                onClick={() => void repost(saved)}
                title="Queue the original again — same caption, same picture. It lands in Review to publish."
              >
                {busy === saved.id ? (
                  <Loader2 className="size-3.5 animate-spin" />
                ) : (
                  <Repeat2 className="size-3.5" />
                )}
                Repost
              </Button>
              <Button
                variant="ghost"
                size="sm"
                className="h-7"
                disabled={busy === saved.id}
                onClick={() => void reuse(saved)}
                title="Write this story again — a fresh hook, caption, first comment and image."
              >
                <Sparkles className="size-3.5" />
                Write again
              </Button>
              {saved.permalink_url ? (
                <a
                  href={saved.permalink_url}
                  target="_blank"
                  rel="noreferrer"
                  title="Open on Facebook"
                  className="rounded p-1.5 text-muted-foreground opacity-0 transition-opacity hover:text-foreground group-hover:opacity-100 focus-visible:opacity-100"
                >
                  <ExternalLink className="size-3.5" />
                </a>
              ) : null}
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
    </div>
  );
}
