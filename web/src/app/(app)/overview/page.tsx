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

import { Loading } from "@/components/loading";
import { QueryError } from "@/components/query-error";
import {
  QUEUE_PAGE_SIZE,
  QueuePagination,
} from "@/components/queue-pagination";
import { Button } from "@/components/ui/button";
import { ScreenHeader } from "@/components/screen";
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
import { body, fullDate, headline, metric, timeAgo } from "@/lib/format";
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
  const { pageId } = usePageScope();
  // The window lives beside the tab switcher because the two share the one
  // pinned summary row — 7/30/60, the totals, and the Performance|Saved tabs
  // all on a single line. That is the whole trick to the header being one row
  // tall instead of two: the query is hoisted to this level so the strip can
  // render before any tab is open.
  const [days, setDays] = useState(30);
  const { data, error, loading, refresh } = useQuery(
    () => getPerformance(pageId!, days),
    [pageId, days],
    { enabled: pageId !== null },
  );

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <ScreenHeader
        title="Overview"
        hint="How this Page's posts did, and the ones worth keeping."
      />

      <Tabs defaultValue="performance" className="flex min-h-0 flex-1 flex-col gap-4">
        {/* The one pinned row: tab switcher, summary strip, then the window
            pill. Together they are the header; nothing above the post list is
            worth a second line. `-mr-3 pr-3` extends the band across the
            scroller's right gutter so nothing bleeds through the gap while it
            is stuck. */}
        <div className="sticky top-0 z-20 -mr-3 bg-background pr-3">
          <div className="flex flex-wrap items-center gap-3">
            <TabsList className="shrink-0">
              <TabsTrigger value="performance">Performance</TabsTrigger>
              <TabsTrigger value="saved">Saved</TabsTrigger>
            </TabsList>

            {!data || data.length === 0 ? null : (
              <>
                {/* The totals, on the same line as the tabs rather than below
                    them — both are context over the list, neither needs its own
                    row. The hint is the strip's tooltip instead of a line of
                    its own. */}
                <Totals
                  posts={data}
                  days={days}
                  hint="Read live from Metricool, best first. The newest posts can still be catching up — their figures lag Facebook by about a day."
                />
                {/* 7 / 30 / 60, and 30 by default. An earlier version defaulted
                    to 90 on the theory that Metricool's lag made shorter
                    windows read as a dead Page — measured against History
                    Retraced, that is false: even over 7 days only 1 post of 28
                    has no reactions yet, and over 30 it is 1 of 219. 90 days is
                    657 rows, which is a scroll rather than an overview.

                    The shared pill, like every other choice-between-alternatives
                    in the app. It was a row of bordered boxes with a
                    `bg-primary/10` active state — a near-white tint barely
                    distinguishable from the inactive ones. */}
                <Tabs
                  value={String(days)}
                  onValueChange={(next) => setDays(Number(next))}
                >
                  <TabsList className="w-fit shrink-0">
                    {[7, 30, 60].map((option) => (
                      <TabsTrigger key={option} value={String(option)}>
                        {option}d
                      </TabsTrigger>
                    ))}
                  </TabsList>
                </Tabs>
              </>
            )}
          </div>
        </div>

        <TabsContent
          value="performance"
          className="min-h-0 flex-1 overflow-y-auto pr-3"
        >
          <Performance days={days} data={data} error={error} loading={loading} refresh={refresh} />
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
 *
 * **Master-detail, rebuilt 2026-08.** The page used to be one column of
 * fat rows — a 112px thumbnail, a headline, a two-line recap, a line of four
 * metrics, engagement, a date and a bookmark, all carrying one row's worth of
 * information. At ten rows a page that read as a crowded ledger with the detail
 * repeated eleven times. The rebuild splits the job onto two columns:
 *
 * - the **list** is now a picker. Each row has only what it takes to choose a
 *   post — rank, a small thumbnail, the headline, the engagement and how long
 *   ago it ran — so ten rows fit on screen and you scan them like a menu;
 * - the **detail** pane on the right holds everything that repeated: the recap,
 *   the full metric breakdown, the exact date, and the actions. It is where you
 *   actually read a post, and it is the same shape whether the list is showing
 *   page one or page six.
 *
 * Why a grid of hero cards was *not* the answer is measured below in
 * `Thumbnail`: the only image Metricool hands back is 130×163, so a card grid
 * would smear it 2.8x across each tile. The detail pane gets to show that tiny
 * image at its native size on a muted backing instead — which is exactly how the
 * Sources screen already handles a 130px source image it must not upscale.
 */
function Performance({
  days,
  data,
  error,
  loading,
  refresh,
}: {
  days: number;
  data: PostStats[] | null;
  error: string | null;
  loading: boolean;
  refresh: () => void;
}) {
  const { pageId } = usePageScope();
  const [busy, setBusy] = useState<string | null>(null);
  // The *pagination* page. The Page is `pageId` — the same collision of names
  // the Review queue has, and named the same way.
  const [page, setPage] = useState(1);
  // Which post the detail pane is showing. A stored id keeps the pane still
  // while you read; it falls back to the page's top row the moment the stored
  // id is not on the page (a page flip, a window change, a save).
  const [selectedId, setSelectedId] = useState<string | null>(null);
  // Reset the pager and the pane when the window changes: page 12 of a 60-day
  // window is nowhere in a 7-day one, and the clamp on its own would land on
  // that window's last page rather than its best posts. Done during render,
  // not in an effect — same reasoning as the page clamp below.
  const [lastDays, setLastDays] = useState(days);
  if (lastDays !== days) {
    setLastDays(days);
    setPage(1);
    setSelectedId(null);
  }

  // Paged, like the queue, and for a sharper version of the queue's reason: 30
  // days is 219 posts on History Retraced and 60 is over 400. The tab is its own
  // scroller, so the whole list rendered — four hundred rows of thumbnail below
  // a totals strip that scrolls away in the first flick.
  const total = data?.length ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / QUEUE_PAGE_SIZE));
  const safePage = Math.min(page, totalPages);
  const shown = data?.slice(
    (safePage - 1) * QUEUE_PAGE_SIZE,
    safePage * QUEUE_PAGE_SIZE,
  );

  // Clamped during render rather than in an effect — `review-list.tsx` sets out
  // why. Here it also covers the window shrinking under the stored page.
  if (page > totalPages) setPage(totalPages);

  // The pane's post. `?? shown?.[0]` makes the top of the current page the
  // default, so selection is never an empty corner even before anyone has
  // clicked. The stored `selectedId` survives a refresh so a save (which re-runs
  // the query) does not jump the pane to row one mid-read.
  const selected = shown?.find((post) => post.post_id === selectedId) ?? shown?.[0] ?? null;
  const selectedRank =
    selected === null ? 0 : (safePage - 1) * QUEUE_PAGE_SIZE + shown!.indexOf(selected) + 1;

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
    <div className="flex flex-col gap-3">
    {loading || !data ? (
      <Loading label="Reading Metricool" className="h-64 rounded-2xl border" />
    ) : data.length === 0 ? (
        <p className="rounded-2xl border border-dashed p-10 text-center text-sm text-muted-foreground">
          Nothing published in this window.
        </p>
      ) : (
        /* Two columns, each sized to its own content (`items-start` — the two
           half-columns are not the same height, and stretching them would pad
           the shorter one with empty framed space). The list page on the left,
           the post being read on the right. */
        <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,5fr)_minmax(0,4fr)]">
          <div className="overflow-hidden rounded-2xl border bg-card">
            {/* The rows keep their own box so `last:border-0` still finds a
                last row. Hung directly off the outer element, the pager may
                become the last child and every row keeps a rule that then
                doubles up against the pager's own. No wrapper padding: the
                rows run edge to edge like a real table. */}
            <div className="flex flex-col">
              {shown?.map((post, index) => (
                <PostRow
                  key={post.post_id}
                  post={post}
                  // Ranked across the whole window, not within the page: the
                  // sort is global, so the first row of page two is 11.
                  rank={(safePage - 1) * QUEUE_PAGE_SIZE + index + 1}
                  selected={selected?.post_id === post.post_id}
                  onSelect={() => setSelectedId(post.post_id)}
                />
              ))}
            </div>
            <QueuePagination
              totalItems={total}
              page={safePage}
              onPageChange={setPage}
            />
          </div>

          <DetailPane
            post={selected}
            rank={selectedRank}
            busy={selected !== null && busy === selected.post_id}
            onSave={selected === null ? undefined : () => void keep(selected)}
          />
        </div>
      )}
    </div>
  );
}

/**
 * What the window adds up to, as one quiet line above the list.
 *
 * These used to be four tall instrument tiles — `min-h-28` each, a whole sticky
 * band of them — which pushed the first post a long scroll below the fold and
 * made the permanent header read as the actual content. An Overview is opened
 * for the posts; the totals are the context, not the feature. So they are now a
 * single mono strip: the same four numbers, at the height of one line, pinned
 * beside the pill so the post list starts almost immediately.
 */
function Totals({ posts, days, hint }: { posts: PostStats[]; days: number; hint?: string }) {
  const reach = posts.reduce((sum, post) => sum + post.impressions, 0);
  const engagement = posts.reduce((sum, post) => sum + post.engagement, 0);

  return (
    <div
      title={hint}
      className="flex min-w-0 flex-1 flex-wrap items-center gap-x-5 gap-y-1 rounded-xl border bg-card px-3.5 py-1.5 font-mono text-[11px] text-muted-foreground"
    >
      <span>
        <strong className="font-medium text-foreground">{metric(posts.length)}</strong>{" "}
        posts · {days}d
      </span>
      <span>
        <strong className="font-medium text-foreground">{metric(reach)}</strong> reach
      </span>
      <span>
        <strong className="font-medium text-foreground">{metric(engagement)}</strong>{" "}
        engagement
      </span>
      <span>
        <strong className="font-medium text-foreground">
          {metric(posts[0]?.engagement ?? 0)}
        </strong>{" "}
        best
      </span>
    </div>
  );
}

/**
 * One row of the picker: just enough to choose a post.
 *
 * The fat row this replaced carried the recap and all four metrics, which the
 * detail pane now holds. What is left is the decision — rank, thumbnail,
 * headline, engagement, age — so ten rows stack into a menu you move through
 * rather than a ledger you read. It is a `<button>` because the row *is* the
 * selection, and the selected row is marked the way SourceCard marks a ticked
 * source: an accent where tiles show gold.
 */
function PostRow({
  post,
  rank,
  selected,
  onSelect,
}: {
  post: PostStats;
  rank: number;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className={cn(
        "flex w-full items-center gap-2.5 border-b px-2 py-1.5 text-left transition-colors last:border-0",
        "hover:bg-muted/40",
        // The selected row reads at a glance, without a ring that fights the
        // row's own padding.
        selected && "bg-gold/[0.08] hover:bg-gold/[0.08]",
      )}
    >
      {/* Rank, not a bullet: the list is sorted, so its position is
          information. Mono and muted — it names the row, it is not a measure. */}
      <span
        className={cn(
          "w-5 shrink-0 text-right font-mono text-[11px]",
          selected ? "font-semibold text-foreground" : "text-muted-foreground",
        )}
      >
        {rank}
      </span>

      <Thumbnail src={post.picture_url} className="w-9" />

      {/* The headline, not the whole caption — the caption is the headline and
          the recap run together, and truncating that names nothing. Same
          treatment the Review queue gives a draft, same helper. */}
      <span className="min-w-0 flex-1 truncate text-sm font-medium">
        {headline(post.text) || "(no text)"}
      </span>

      {/* The two numbers the list is ordered and timed by, right-aligned so they
          read down the side of the column. `tabular-nums` for the one column
          that has to line up across ten rows. */}
      <span className="shrink-0 text-sm font-semibold tabular-nums">
        {metric(post.engagement)}
      </span>
      <span className="shrink-0 font-mono text-[10px] text-muted-foreground">
        {timeAgo(post.published_at)}
      </span>
    </button>
  );
}

/**
 * The right-hand pane: the post the picker has landed on, read whole.
 *
 * This is where the recap, the metric breakdown, the exact date and the actions
 * all live now — nothing a row of the list repeats any more. The layout leans on
 * the one image constraint that shaped the whole rebuild:
 *
 * - the picture is centred at (near) native size on a muted backing, the same
 *   treatment `source-card.tsx` gives a 130px source it must not upscale, rather
 *   than stretched across a tile it would smear;
 * - the headline is the big thing, as it should be for the one post being read;
 * - the four metrics are a tile row in the same instrument language as the
 *   totals above, so the screen reads as one system.
 */
function DetailPane({
  post,
  rank,
  busy,
  onSave,
}: {
  post: PostStats | null;
  rank: number;
  busy: boolean;
  onSave?: () => void;
}) {
  return (
    <div className="flex flex-col overflow-hidden rounded-2xl border bg-card">
      <div className="flex items-center justify-between gap-3 border-b px-4 py-3">
        <p className="font-mono text-[11px] tracking-[0.12em] text-muted-foreground uppercase">
          Post detail
        </p>
        <span className="font-mono text-[11px] text-muted-foreground/70">
          {post ? `#${rank}` : ""}
        </span>
      </div>

      {post ? (
        <>
        <div className="flex gap-4 p-4">
          {/* A fixed-width column, not a full-width row: the image is 128px
              and the pane is ~600px, so centring it on its own line left
              most of that width unused. A column gives the caption and stats
              the width, and the dressing that used to frame the image is now
              the card edge instead of a hard box behind it. */}
          <Thumbnail src={post.picture_url} className="w-28 shrink-0" />

          <div className="min-w-0 flex-1">
            <h2 className="text-base font-semibold tracking-tight leading-snug">
              {headline(post.text) || "(no text)"}
            </h2>
            {/* The recap, compact. It is a *preview* here — the full caption is
                a click on Open away — because the pane must fit next to the
                picker without scroll. Five lines still tells two posts on the
                same subject apart. */}
            <p className="line-clamp-6 pt-1.5 text-[13px] leading-relaxed text-muted-foreground">
              {body(post.text) || "No caption."}
            </p>
          </div>
        </div>

        <div className="p-4">
          {/* Breakdown in the same tile language as the totals above. */}
          <div className="grid grid-cols-4 gap-px overflow-hidden rounded-xl border bg-border">
            <DetailStat label="Reactions" value={metric(post.reactions)} />
            <DetailStat label="Comments" value={metric(post.comments)} />
            <DetailStat label="Shares" value={metric(post.shares)} />
            <DetailStat label="Reach" value={metric(post.impressions)} sub="impressions" />
          </div>

          <p className="pt-2.5 text-[11px] text-muted-foreground">
            Engagement <strong className="font-semibold text-foreground">{metric(post.engagement)}</strong>
            {" · "}
            <span title={fullDate(post.published_at)}>{timeAgo(post.published_at)}</span>
          </p>

          <div className="mt-3 flex items-center gap-2 border-t pt-3">
            {post.permalink_url ? (
              <Button variant="outline" size="sm" asChild>
                <a href={post.permalink_url} target="_blank" rel="noreferrer">
                  <ExternalLink className="size-3.5" />
                  Open on Facebook
                </a>
              </Button>
            ) : null}
            <Button
              variant="ghost"
              size="sm"
              onClick={onSave}
              disabled={busy || post.saved || !onSave}
              title={post.saved ? "Already saved" : "Keep this post for reference"}
            >
              {busy ? (
                <Loader2 className="size-3.5 animate-spin" />
              ) : post.saved ? (
                <BookmarkCheck className="size-3.5" />
              ) : (
                <Bookmark className="size-3.5" />
              )}
              {post.saved ? "Saved" : "Save for reference"}
            </Button>
          </div>
        </div>
        </>
      ) : (
        <p className="p-4 text-sm text-muted-foreground">Select a post to read it here.</p>
      )}
    </div>
  );
}

/** One cell of the detail pane's breakdown. */
function DetailStat({
  label,
  value,
  sub,
}: {
  label: string;
  value: string;
  sub?: string;
}) {
  return (
    <div className="bg-card px-3 py-2.5">
      <p className="font-mono text-[10px] tracking-[0.12em] text-muted-foreground uppercase">
        {label}
      </p>
      <p className="pt-0.5 text-xl font-semibold tabular-nums">{value}</p>
      {sub ? (
        <p className="font-mono text-[10px] text-muted-foreground/70">{sub}</p>
      ) : null}
    </div>
  );
}

/**
 * The post's picture, or a stand-in.
 *
 * Facebook's CDN URLs are signed and expire — the same trap the competitor
 * pictures document — so a missing thumbnail is the expected end state rather
 * than a fault. The row carries its numbers either way.
 *
 * **4:5 and the size are both measured rather than chosen.** Measured 2026-08-18
 * on History Retraced's 30-day window: the file the CDN serves is **130 x 163**,
 * and that is the only file there is — Metricool's `fullPicture` is null on
 * every row, and the signed URL answers 403 to any edit of its `stp` size
 * directive. The composite is 4:5, so that is the box shape (`object-cover`
 * on a square cut the top and bottom off every thumbnail — exactly where the
 * hook text is painted). The size stays the caller's: `w-12` for a picker row,
 * `size-32` (128px, just under native) for the detail pane — never larger,
 * because past ~130px the upscale starts to smear.
 */
function Thumbnail({ src, className }: { src: string | null; className?: string }) {
  if (!src) {
    return (
      <div
        className={cn(
          "flex aspect-4/5 shrink-0 items-center justify-center rounded-xl border bg-muted",
          className,
        )}
      >
        <BarChart3 className="size-4 text-muted-foreground/50" />
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
      className={cn(
        "aspect-4/5 shrink-0 rounded-xl border object-cover bg-muted",
        className,
      )}
    />
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
  // The pagination page, as in Performance and the Review queue.
  const [page, setPage] = useState(1);
  // Which saved post the pane shows — the Performance selection's twin.
  const [selectedId, setSelectedId] = useState<number | null>(null);

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
        // `/review/{id}`, not `/review?draft={id}`. The drawer is a *route* —
        // being on `/review/12` is what open means (`draft-sheet.tsx`) — so the
        // query string matched nothing, opened nothing, and dropped the
        // operator on the bare queue wondering where their repost went.
        action: { label: "Review", onClick: () => router.push(`/review/${draft.id}`) },
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
  if (loading || !data)
    return <Loading label="Loading saved posts" className="h-64 rounded-2xl border" />;

  if (data.length === 0) {
    return (
      <p className="rounded-2xl border border-dashed p-10 text-center text-sm text-muted-foreground">
        Nothing saved yet. Keep a post from the Performance tab and it stays
        here — including after it drops out of the reporting window.
      </p>
    );
  }

  const totalPages = Math.max(1, Math.ceil(data.length / QUEUE_PAGE_SIZE));
  const safePage = Math.min(page, totalPages);
  const shown = data.slice(
    (safePage - 1) * QUEUE_PAGE_SIZE,
    safePage * QUEUE_PAGE_SIZE,
  );

  // Removing the last saved post on the last page would otherwise strand the
  // list on a page that no longer exists. Clamped during render, not in an
  // effect — `review-list.tsx` sets out why.
  if (page > totalPages) setPage(totalPages);

  // The pane's post, defaulting to the top of the page — same rule as
  // Performance. A removed post falls out of `shown` and the next top row takes
  // the pane.
  const selected = shown.find((saved) => saved.id === selectedId) ?? shown[0] ?? null;

  return (
    <div className="flex flex-col gap-3">
      <p className="text-xs text-muted-foreground">
        The numbers below are what each post had scored when it was saved, not a
        live figure. <strong className="font-medium text-foreground">Repost</strong>{" "}
        queues the original caption and picture; <strong className="font-medium text-foreground">Write again</strong>{" "}
        sends the story back through the writer for a fresh one.
      </p>

      <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,5fr)_minmax(0,4fr)]">
        <div className="overflow-hidden rounded-2xl border bg-card">
          {/* The rows keep their own box so `last:border-0` still finds a last
              row — see the same note in Performance. */}
          <div className="flex flex-col">
            {shown.map((saved) => (
              <SavedRow
                key={saved.id}
                saved={saved}
                selected={selected?.id === saved.id}
                onSelect={() => setSelectedId(saved.id)}
              />
            ))}
          </div>
          <QueuePagination
            totalItems={data.length}
            page={safePage}
            onPageChange={setPage}
          />
        </div>

        <SavedDetailPane
          saved={selected}
          busy={selected !== null && busy === selected.id}
          onRepost={selected === null ? undefined : () => void repost(selected)}
          onReuse={selected === null ? undefined : () => void reuse(selected)}
          onRemove={selected === null ? undefined : () => void drop(selected)}
        />
      </div>
    </div>
  );
}

/** A picker row for a saved post — the Performance row's shape. */
function SavedRow({
  saved,
  selected,
  onSelect,
}: {
  saved: SavedPost;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className={cn(
        "flex w-full items-center gap-2.5 border-b px-2 py-1.5 text-left transition-colors last:border-0",
        "hover:bg-muted/40",
        selected && "bg-gold/[0.08] hover:bg-gold/[0.08]",
      )}
    >
      <Thumbnail src={saved.picture_url} className="w-9" />
      <span className="min-w-0 flex-1 truncate text-sm font-medium">
        {headline(saved.text) || "(no text)"}
      </span>
      {/* The client's ask: "there needs to be a visible date showing how many
          days ago it was posted last." Relative, because that is the question —
          whether it is far enough back to run again — and the exact stamp is a
          hover away rather than a second line nobody reads. */}
      <span
        className="shrink-0 text-xs text-muted-foreground"
        title={fullDate(saved.published_at)}
      >
        {timeAgo(saved.published_at)}
      </span>
      <span className="shrink-0 text-sm font-semibold tabular-nums">
        {metric(saved.reactions)}
      </span>
    </button>
  );
}

/**
 * The saved post being read — the Performance pane, with the actions that make
 * a *saved* post different: Repost back to the queue, or send the story through
 * the writer again.
 */
function SavedDetailPane({
  saved,
  busy,
  onRepost,
  onReuse,
  onRemove,
}: {
  saved: SavedPost | null;
  busy: boolean;
  onRepost?: () => void;
  onReuse?: () => void;
  onRemove?: () => void;
}) {
  return (
    <div className="flex flex-col overflow-hidden rounded-2xl border bg-card">
      <div className="flex items-center justify-between gap-3 border-b px-4 py-3">
        <p className="font-mono text-[11px] tracking-[0.12em] text-muted-foreground uppercase">
          Saved post
        </p>
      </div>

      {saved ? (
        <>
        <div className="flex gap-4 p-4">
          {/* Image as a fixed-width column, as on the Performance pane. */}
          <Thumbnail src={saved.picture_url} className="w-28 shrink-0" />

          <div className="min-w-0 flex-1">
            <h2 className="text-base font-semibold tracking-tight leading-snug">
              {headline(saved.text) || "(no text)"}
            </h2>
            {/* Same compact recap as the Performance pane: a preview, with the
                full caption a click away on Open. */}
            <p className="line-clamp-6 pt-1.5 text-[13px] leading-relaxed text-muted-foreground">
              {body(saved.text) || "No caption."}
            </p>
          </div>
        </div>

        <div className="grid grid-cols-4 gap-px overflow-hidden rounded-xl border bg-border p-4">
            <DetailStat label="Reactions" value={metric(saved.reactions)} />
            <DetailStat label="Comments" value={metric(saved.comments)} />
            <DetailStat label="Shares" value={metric(saved.shares)} />
            <DetailStat label="Reach" value={metric(saved.impressions)} sub="impressions" />
          </div>

          <p className="pt-2.5 text-[11px] text-muted-foreground">
            Saved <span title={fullDate(saved.created_at)}>{timeAgo(saved.created_at)}</span>
            {" · "}
            last posted <span title={fullDate(saved.published_at)}>{timeAgo(saved.published_at)}</span>
          </p>

          <div className="mt-3 flex flex-wrap items-center gap-2 border-t pt-3">
            <Button
              variant="default"
              size="sm"
              disabled={busy}
              onClick={onRepost}
              title="Queue the original again — same caption, same picture. It lands in Review to publish."
            >
              {busy ? <Loader2 className="size-3.5 animate-spin" /> : <Repeat2 className="size-3.5" />}
              Repost
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={busy}
              onClick={onReuse}
              title="Write this story again — a fresh hook, caption, first comment and image."
            >
              <Sparkles className="size-3.5" />
              Write again
            </Button>
            {saved.permalink_url ? (
              <Button variant="ghost" size="sm" asChild>
                <a href={saved.permalink_url} target="_blank" rel="noreferrer">
                  <ExternalLink className="size-3.5" />
                  Open
                </a>
              </Button>
            ) : null}
            <Button
              variant="ghost"
              size="sm"
              onClick={onRemove}
              className="ml-auto text-destructive hover:bg-destructive/10 hover:text-destructive"
              title="Stop keeping this post"
            >
              <BookmarkCheck className="size-3.5" />
              Remove
            </Button>
          </div>
        </>
      ) : (
        <p className="p-4 text-sm text-muted-foreground">Select a post to read it here.</p>
      )}
    </div>
  );
}
