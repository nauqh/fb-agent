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
  // The window: 7/30/60, defaulting to 30 (why, measured, is on the pill
  // below). The query is hoisted to this level so the pill can render before
  // any tab is open — the same reason the band and the lists live under the
  // Tabs above rather than in a screen of their own.
  const [days, setDays] = useState(30);
  const { data, error, loading, refresh } = useQuery(
    () => getPerformance(pageId!, days),
    [pageId, days],
    { enabled: pageId !== null },
  );

  // Which tab is open, held here rather than left to `defaultValue`, because
  // the summary band beside the switcher belongs to Performance alone: its
  // totals and its 7/30/60 window say nothing about the saved list, and left
  // on screen over the Saved tab they read as that tab's numbers.
  const [tab, setTab] = useState("performance");

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {/* No hint line. "How this Page's posts did, and the ones worth keeping"
          is what the two tabs directly below already say, and no other screen
          carries one. */}
      <ScreenHeader title="Overview" />

      <Tabs
        value={tab}
        onValueChange={setTab}
        className="flex min-h-0 flex-1 flex-col gap-4"
      >
        {/* The one pinned row: tab switcher, then the window pill. Together
            they are the header. The KPI band and the post regions below own
            the scroll; only the control that says *what* you are looking at
            stays stuck. `-mr-3 pr-3` extends the band across the scroller's
            right gutter so nothing bleeds through the gap while it is stuck. */}
        <div className="sticky top-0 z-20 -mr-3 bg-background pr-3">
          <div className="flex flex-wrap items-center gap-3">
            <TabsList className="shrink-0">
              <TabsTrigger value="performance">Performance</TabsTrigger>
              <TabsTrigger value="saved">Saved</TabsTrigger>
            </TabsList>

            {/* 7 / 30 / 60, and 30 by default. An earlier version defaulted to
                90 on the theory that Metricool's lag made shorter windows read
                as a dead Page — measured against History Retraced, that is
                false: even over 7 days only 1 post of 28 has no reactions yet,
                and over 30 it is 1 of 219. 90 days is 657 rows, which is a
                scroll rather than an overview.

                The shared pill, like every other choice-between-alternatives in
                the app. It was a row of bordered boxes with a `bg-primary/10`
                active state — a near-white tint barely distinguishable from the
                inactive ones. Lives here, beside the tabs and above the band it
                filters, on the Performance tab only. */}
            {tab === "performance" && data && data.length > 0 ? (
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
            ) : null}
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
 * **Bento, rebuilt 2026-08.** The page used to be one column of fat rows — a
 * 112px thumbnail, a headline, a two-line recap, a line of four metrics,
 * engagement, a date and a bookmark, all carrying one row's worth of
 * information. At ten rows a page that read as a crowded ledger with the detail
 * repeated eleven times. A later rebuild split that onto two columns — a picker
 * list and a detail pane — which is where this rework started. The screen now
 * reads as three distinct regions rather than one repeated list:
 *
 * - **Region one** is the KPI band: what the window adds up to, one
 *   segmented instrument (posts / reach / engagement) above everything;
 * - **Region two** is the lead strip: the post the list is pointing at,
 *   promoted full-width — image at native size, headline, recap, the four
 *   metrics and the actions, all in the open;
 * - **Region three** is the ranked list as a data table: rank, small
 *   thumbnail, headline, then the four numbers down their own right-aligned
 *   columns, so a page scans as a table before a single row is clicked.
 *
 * Why a grid of hero cards was *not* the answer is measured below in
 * `Thumbnail`: the only image Metricool hands back is 130×163, so a card grid
 * would smear it 2.8x across each tile. The lead strip shows that tiny image
 * at its native size on a muted backing instead — which is exactly how the
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
  // Its rank across the whole window (the sort is global, so index in `data`
  // is the rank). The lead badge and the promoted row both print it.
  const selectedRank =
    selected === null ? null : (data?.indexOf(selected) ?? -1) + 1;

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
    <div className="flex flex-col gap-4">
    {loading || !data ? (
      <Loading label="Reading Metricool" className="h-64 rounded-xl border" />
    ) : data.length === 0 ? (
        <p className="rounded-xl border border-dashed p-10 text-center text-sm text-muted-foreground">
          Nothing published in this window.
        </p>
      ) : (
        <>
          {/* Region one: what the window adds up to, as one segmented
              instrument rather than three floating tiles. It is a single
              card with hairline dividers, mono labels and tabular figures —
              the app's own measure language — so the columns read as cells of
              one object and the band never competes with the posts below.
              The hint rides here as the band's tooltip. */}
          <KpiBand
            posts={data}
            hint="Read live from Metricool, best first. The newest posts can still be catching up — their figures lag Facebook by about a day."
          />

          {/* Region two: the post you are reading, promoted to a lead strip
              spanning the page. The selected row's numbers are not hidden in a
              side pane any more — the strip is the pane laid on its side, so
              the breakdown and the actions sit in the open above the list. */}
          <LeadFeature
            post={selected}
            rank={selectedRank}
            busy={selected !== null && busy === selected.post_id}
            onSave={selected === null ? undefined : () => void keep(selected)}
          />

          {/* Region three: the full ranked list, now a data table — rank,
              thumb, headline, then the four numbers, laid right-aligned down
              their own columns so a page reads as a table before a single row
              is clicked. The detail pane exists to unload these from the rows;
              the table puts them back, because with the strip above carrying
              the breakdown the rows can afford to be scannable instead of
              terse. Columns hide below `lg` where they would crowd the
              headline. */}
          <div className="overflow-hidden rounded-xl border bg-card">
            {/* Column headers, `lg` only — the four numbers below them would
                otherwise read as a wall of figures. Right-aligned to the same
                widths the columns use, mono and muted like every other label;
                they are furniture, not data, and they disappear below `lg`
                where the columns do too. `aria-hidden`: the digits read fine
                without the labels in a screen reader, which already gets them
                as part of a row's meaning. */}
            <div
              aria-hidden
              className="hidden items-center gap-2.5 border-b bg-muted/30 px-2 py-1.5 lg:flex"
            >
              <span className="w-5 shrink-0" />
              <span className="w-9 shrink-0" />
              <span className="min-w-0 flex-1" />
              <span className="hidden w-14 shrink-0 text-right font-mono text-[10px] tracking-[0.12em] text-muted-foreground uppercase lg:block">
                Reac.
              </span>
              <span className="hidden w-14 shrink-0 text-right font-mono text-[10px] tracking-[0.12em] text-muted-foreground uppercase lg:block">
                Com.
              </span>
              <span className="hidden w-14 shrink-0 text-right font-mono text-[10px] tracking-[0.12em] text-muted-foreground uppercase lg:block">
                Shares
              </span>
              <span className="hidden w-14 shrink-0 text-right font-mono text-[10px] tracking-[0.12em] text-muted-foreground uppercase lg:block">
                Reach
              </span>
              <span className="shrink-0 lg:w-16" />
              <span className="shrink-0 lg:w-24" />
            </div>
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
        </>
      )}
    </div>
  );
}

/**
 * What the window adds up to, as one segmented instrument above the list.
 *
 * These used to be four tall instrument tiles — `min-h-28` each, a whole sticky
 * band of them — which pushed the first post a long scroll below the fold and
 * made the permanent header read as the actual content. An Overview is opened
 * for the posts; the totals are the context, not the feature. So they shrank to
 * a quiet mono strip, then grew back into a single bordered card.
 *
 * The card is one object, not three tiles: hairline dividers between its cells,
 * mono uppercase labels and tabular figures, all on one `bg-card` ground. Read
 * as a gauge strip rather than a dashboard of floating cards, it says "this
 * window's totals" in the same instrument language the detail pane's breakdown
 * uses, so the screen reads as one system.
 *
 * Three now, not four. "11.7K best" was the first row of the list it sits on
 * top of, and "228 posts · 30d" repeated the window off the pill two controls
 * to its right — both were the same figure said twice on one line.
 */
function KpiBand({ posts, hint }: { posts: PostStats[]; hint?: string }) {
  const reach = posts.reduce((sum, post) => sum + post.impressions, 0);
  const engagement = posts.reduce((sum, post) => sum + post.engagement, 0);

  return (
    <div
      title={hint}
      className="grid grid-cols-3 divide-x divide-border overflow-hidden rounded-xl border bg-card"
    >
      <KpiCell label="Posts" value={metric(posts.length)} />
      <KpiCell label="Reach" value={metric(reach)} />
      <KpiCell label="Engagement" value={metric(engagement)} />
    </div>
  );
}

/** One cell of the totals band: an uppercase mono label and a tabular figure. */
function KpiCell({ label, value }: { label: string; value: string }) {
  return (
    <div className="px-4 py-3">
      <p className="font-mono text-[10px] tracking-[0.12em] text-muted-foreground uppercase">
        {label}
      </p>
      <p className="pt-1 text-2xl font-semibold tracking-tight tabular-nums">
        {value}
      </p>
    </div>
  );
}

/**
 * One row of the ranked list, now a data table.
 *
 * The row used to be a picker — rank, thumb, headline, engagement, age — with
 * the full breakdown parked in a side pane. With the pane replaced by the lead
 * strip above, the table can afford to show the numbers: reactions, comments,
 * shares and reach run right-aligned down their own columns (`tabular-nums`)
 * so a page scans as a table before a single row is clicked, and engagement
 * stays the emphasised column the sort is by. Columns drop below `lg`, where
 * they would crowd the headline; the strip above still carries them.
 *
 * It is a `<button>` because the row *is* the selection: clicking promotes the
 * post into the lead strip. The selected row is marked the way SourceCard marks
 * a ticked source: an accent where tiles show gold.
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
        "flex w-full items-center gap-2.5 border-b px-2 py-1.5 text-left transition-colors outline-none last:border-0",
        "hover:bg-muted/40",
        // Inset, not the browser default: the list's own `overflow-hidden`
        // clips an outset outline to a sliver on whichever edge touches the
        // card, so a keyboard user tabbing the picker sees almost nothing.
        "focus-visible:ring-ring/50 focus-visible:ring-2 focus-visible:ring-inset",
        // The selected row reads at a glance, without a ring that fights the
        // row's own padding.
        selected && "bg-gold/[0.08] hover:bg-gold/[0.08]",
      )}
    >
      {/* Rank, not a bullet: the list is sorted, so its position is
          information. Mono and muted — it names the row, it is not a measure. The
          top three read in gold, the one warm accent the app owns: it is the
          same yellow painted into the published images, so "top of the Page"
          and "the post itself" share one colour. */}
      <span
        className={cn(
          "w-5 shrink-0 text-right font-mono text-[11px] tabular-nums",
          rank <= 3
            ? "font-semibold text-gold"
            : selected
              ? "font-semibold text-foreground"
              : "text-muted-foreground",
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

      {/* The four numbers laid down the side, right-aligned so they read as
          columns. `tabular-nums` for the ones that must line up across ten
          rows. `max-lg:hidden` on each: below `lg` they would crowd the
          headline, and the lead strip above still carries the breakdown. */}
      <span className="hidden w-14 shrink-0 text-right font-mono text-[11px] text-muted-foreground tabular-nums lg:block">
        {metric(post.reactions)}
      </span>
      <span className="hidden w-14 shrink-0 text-right font-mono text-[11px] text-muted-foreground tabular-nums lg:block">
        {metric(post.comments)}
      </span>
      <span className="hidden w-14 shrink-0 text-right font-mono text-[11px] text-muted-foreground tabular-nums lg:block">
        {metric(post.shares)}
      </span>
      <span className="hidden w-14 shrink-0 text-right font-mono text-[11px] text-muted-foreground tabular-nums lg:block">
        {metric(post.impressions)}
      </span>
      {/* Engagement stays the emphasised column — it is the figure the list is
          ordered by, so it earns the semibold. Fixed width on `lg` (the header
          row above shares it) so the column lines up down the page. */}
      <span className="shrink-0 text-sm font-semibold tabular-nums lg:w-16">
        {metric(post.engagement)}
      </span>
      <span className="shrink-0 font-mono text-[10px] text-muted-foreground lg:w-24">
        {timeAgo(post.published_at)}
      </span>
    </button>
  );
}

/**
 * The post the list is pointing at, promoted to a lead strip across the page.
 *
 * The rebuild replaced the side pane with a full-width strip, for two reasons:
 * a head-to-head reader rarely wants to scroll a tall side pane while the list
 * moves beneath it, and a wide strip lets the breakdown and the actions sit on
 * the same horizontal line as the reading — image, copy, the four tiles, the
 * buttons, no vertical scroll of detail to get to the next decision.
 *
 * The one image constraint shaped the layout: the file is 130×163 and must not
 * be upscaled, so the picture stays a ~128px column on a muted backing, the
 * same treatment `source-card.tsx` gives a 130px source. The rank badge lifts
 * off the thumb; the headline is the big thing; the four metrics are a tile row
 * in the same instrument language as the totals band, so the page reads as one
 * system. The strip stays in flow — it is the context the list scrolls past,
 * not a pane that should overlay it.
 */
function LeadFeature({
  post,
  rank,
  busy,
  onSave,
}: {
  post: PostStats | null;
  rank: number | null;
  busy: boolean;
  onSave?: () => void;
}) {
  return (
    // No "POST DETAIL" header bar, and no rank in a header: the badge carries
    // it, and the highlighted row below already prints the same number.
    <div className="flex flex-col overflow-hidden rounded-xl border bg-card">
      {post ? (
        <>
        <div className="flex gap-4 p-4 sm:gap-5 sm:p-5">
          {/* A fixed-width column: the image is 128px and the strip is full
              width, so the column keeps the strip from leaving the image to
              hang in whitespace. The badge sits at the image's top corner,
              ringed in card so it lifts off the thumb rather than bleeding
              into it. */}
          <div className="relative shrink-0 self-start">
            <Thumbnail src={post.picture_url} className="w-28 sm:w-32" />
            {rank === null ? null : (
              <span className="absolute -top-1.5 -left-1.5 flex size-6 items-center justify-center rounded-full bg-foreground font-mono text-[10px] font-medium text-background ring-2 ring-card">
                {rank}
              </span>
            )}
          </div>

          <div className="min-w-0 flex-1">
            <h2 className="text-base font-semibold tracking-tight leading-snug sm:text-lg">
              {headline(post.text) || "(no text)"}
            </h2>
            {/* The recap, compact. A preview — the full caption is a click on
                Open away — because the strip must lead the eye to the list,
                not hold it. Three lines still tells two posts on the same
                subject apart. */}
            <p className="line-clamp-3 pt-1.5 text-[13px] leading-relaxed text-muted-foreground">
              {body(post.text) || "No caption."}
            </p>

            <p className="pt-2.5 text-[11px] text-muted-foreground">
              Engagement{" "}
              <strong className="font-semibold text-foreground">
                {metric(post.engagement)}
              </strong>
              {" · "}
              <span title={fullDate(post.published_at)}>
                {timeAgo(post.published_at)}
              </span>
            </p>
          </div>
        </div>

        {/* The breakdown and the actions share the lower half of the strip,
            divided where the reading ends and the deciding begins. The tiles
            keep the instrument language of the totals band; the buttons keep
            the one-word-per-action convention. */}
        <div className="flex flex-col gap-3 border-t px-4 py-3 sm:flex-row sm:items-center sm:justify-between sm:px-5">
          <div className="grid grid-cols-4 gap-px overflow-hidden self-stretch rounded-lg border bg-border sm:self-auto">
            <DetailStat label="Reactions" value={metric(post.reactions)} />
            <DetailStat label="Comments" value={metric(post.comments)} />
            <DetailStat label="Shares" value={metric(post.shares)} />
            {/* "impressions" under Reach said the same word twice. */}
            <DetailStat label="Reach" value={metric(post.impressions)} />
          </div>

          <div className="flex shrink-0 items-center gap-2">
            {post.permalink_url ? (
              <Button variant="outline" size="sm" asChild title="Open this post on Facebook">
                <a href={post.permalink_url} target="_blank" rel="noreferrer">
                  <ExternalLink className="size-3.5" />
                  Open
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
              {post.saved ? "Saved" : "Save"}
            </Button>
          </div>
        </div>
        </>
      ) : (
        <p className="p-4 text-sm text-muted-foreground">Select a post.</p>
      )}
    </div>
  );
}

/** One cell of the detail pane's breakdown: a label and a number, nothing else. */
function DetailStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-card px-3 py-2.5">
      <p className="font-mono text-[10px] tracking-[0.12em] text-muted-foreground uppercase">
        {label}
      </p>
      <p className="pt-0.5 text-xl font-semibold tabular-nums">{value}</p>
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
 * hook text is painted). The size stays the caller's: `w-9` for a table row,
 * `w-28 sm:w-32` (128px, just under native) for a lead strip — never larger,
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
    return <Loading label="Loading saved posts" className="h-64 rounded-xl border" />;

  if (data.length === 0) {
    return (
      <p className="rounded-xl border border-dashed p-10 text-center text-sm text-muted-foreground">
        Nothing saved yet. Keep a post from Performance and it stays here.
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
    // No standing paragraph above the list. It explained Repost and Write
    // again, which are two labelled buttons carrying that same sentence as
    // their tooltip, and warned that the stats are a snapshot — now the
    // tooltip on the stat row that the warning is about.
    <div className="flex flex-col gap-4">
      {/* The saved post being read, promoted to the same full-width strip the
          Performance tab gives its lead — image, copy, the snapshot stats and
          the actions that make a *saved* post different. */}
      <SavedLeadStrip
        saved={selected}
        busy={selected !== null && busy === selected.id}
        onRepost={selected === null ? undefined : () => void repost(selected)}
        onReuse={selected === null ? undefined : () => void reuse(selected)}
        onRemove={selected === null ? undefined : () => void drop(selected)}
      />

      {/* The saved list, as a data table — the Performance table, with the
          same four columns and the age where engagement stood. */}
      <div className="overflow-hidden rounded-xl border bg-card">
        <div aria-hidden className="hidden items-center gap-2.5 border-b bg-muted/30 px-2 py-1.5 lg:flex">
          <span className="w-9 shrink-0" />
          <span className="min-w-0 flex-1" />
          <span className="hidden w-14 shrink-0 text-right font-mono text-[10px] tracking-[0.12em] text-muted-foreground uppercase lg:block">
            Reac.
          </span>
          <span className="hidden w-14 shrink-0 text-right font-mono text-[10px] tracking-[0.12em] text-muted-foreground uppercase lg:block">
            Com.
          </span>
          <span className="hidden w-14 shrink-0 text-right font-mono text-[10px] tracking-[0.12em] text-muted-foreground uppercase lg:block">
            Shares
          </span>
          <span className="hidden w-14 shrink-0 text-right font-mono text-[10px] tracking-[0.12em] text-muted-foreground uppercase lg:block">
            Reach
          </span>
          <span className="shrink-0 lg:w-24" />
        </div>
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
    </div>
  );
}

/** A row of the saved table — the Performance row, with the age where its
 *  engagement stood (a saved post's snapshot has no engagement figure). */
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
        "flex w-full items-center gap-2.5 border-b px-2 py-1.5 text-left transition-colors outline-none last:border-0",
        "hover:bg-muted/40",
        // Same inset ring as PostRow, and the same reason: an outset ring
        // gets clipped by the list card's `overflow-hidden`.
        "focus-visible:ring-ring/50 focus-visible:ring-2 focus-visible:ring-inset",
        selected && "bg-gold/[0.08] hover:bg-gold/[0.08]",
      )}
    >
      <Thumbnail src={saved.picture_url} className="w-9" />
      <span className="min-w-0 flex-1 truncate text-sm font-medium">
        {headline(saved.text) || "(no text)"}
      </span>
      {/* The four snapshot numbers, in the Performance table's columns. */}
      <span className="hidden w-14 shrink-0 text-right font-mono text-[11px] text-muted-foreground tabular-nums lg:block">
        {metric(saved.reactions)}
      </span>
      <span className="hidden w-14 shrink-0 text-right font-mono text-[11px] text-muted-foreground tabular-nums lg:block">
        {metric(saved.comments)}
      </span>
      <span className="hidden w-14 shrink-0 text-right font-mono text-[11px] text-muted-foreground tabular-nums lg:block">
        {metric(saved.shares)}
      </span>
      <span className="hidden w-14 shrink-0 text-right font-mono text-[11px] text-muted-foreground tabular-nums lg:block">
        {metric(saved.impressions)}
      </span>
      {/* The client's ask: "there needs to be a visible date showing how many
          days ago it was posted last." Relative, because that is the question —
          whether it is far enough back to run again — and the exact stamp is a
          hover away rather than a second line nobody reads. */}
      <span
        className="shrink-0 text-xs text-muted-foreground lg:w-24"
        title={fullDate(saved.published_at)}
      >
        {timeAgo(saved.published_at)}
      </span>
    </button>
  );
}

/**
 * The saved post being read — the same full-width strip the Performance tab
 * gives its lead, with the actions that make a *saved* post different: Repost
 * back to the queue, or send the story through the writer again.
 */
function SavedLeadStrip({
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
    // No header bar, as on the Performance strip.
    <div className="flex flex-col overflow-hidden rounded-xl border bg-card">
      {saved ? (
        <>
        <div className="flex gap-4 p-4 sm:gap-5 sm:p-5">
          {/* Image as a fixed-width column, as on the Performance strip. */}
          <Thumbnail src={saved.picture_url} className="w-28 shrink-0 sm:w-32" />

          <div className="min-w-0 flex-1">
            <h2 className="text-base font-semibold tracking-tight leading-snug sm:text-lg">
              {headline(saved.text) || "(no text)"}
            </h2>
            {/* Same compact recap as the Performance strip: a preview, with the
                full caption a click away on Open. */}
            <p className="line-clamp-3 pt-1.5 text-[13px] leading-relaxed text-muted-foreground">
              {body(saved.text) || "No caption."}
            </p>

            <p className="pt-2.5 text-[11px] text-muted-foreground">
              Saved <span title={fullDate(saved.created_at)}>{timeAgo(saved.created_at)}</span>
              {" · "}
              last posted <span title={fullDate(saved.published_at)}>{timeAgo(saved.published_at)}</span>
            </p>
          </div>
        </div>

        {/* The snapshot tiles and the actions share the strip's lower bar —
            the same division as the Performance strip. The snapshot warning is
            this row's tooltip rather than a line of prose above the tab: it is
            only ever about these four numbers. */}
        <div className="flex flex-col gap-3 border-t px-4 py-3 sm:flex-row sm:items-center sm:justify-between sm:px-5">
          <div
            title="What the post had scored when it was saved, not a live figure."
            className="grid grid-cols-4 gap-px overflow-hidden self-stretch rounded-lg border bg-border sm:self-auto"
          >
            <DetailStat label="Reactions" value={metric(saved.reactions)} />
            <DetailStat label="Comments" value={metric(saved.comments)} />
            <DetailStat label="Shares" value={metric(saved.shares)} />
            <DetailStat label="Reach" value={metric(saved.impressions)} />
          </div>

          <div className="flex shrink-0 flex-wrap items-center gap-2">
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
        </div>
        </>
      ) : (
        <p className="p-4 text-sm text-muted-foreground">Select a post.</p>
      )}
    </div>
  );
}
