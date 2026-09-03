"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  BarChart3,
  Bookmark,
  BookmarkCheck,
  ChevronRight,
  ExternalLink,
  Loader2,
  Repeat2,
  Sparkles,
  TrendingDown,
  TrendingUp,
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
  getPerformanceWindow,
  listSaved,
  savePost,
  repostSaved,
  reuseSaved,
  unsavePost,
  type PerformanceWindow,
  type PostStats,
  type SavedPost,
} from "@/lib/api/overview";
import { fullDate, headline, metric, timeAgo } from "@/lib/format";
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
 *
 * **The table is the screen, rebuilt 2026-09.** The previous pass put a totals
 * band and a full-width lead strip above the list. Measured on the real screen
 * at 1440x900: those two cost about 500px before the first post, the band held
 * three six-character numbers in a 1300px box, and the strip printed the
 * selected post's five figures a hundred pixels above the same five figures in
 * the row it came from. An Overview is opened for the posts. So the totals
 * collapsed to one line of text, the strip is gone, and the detail it carried
 * now opens **inside the row it belongs to** — the panel grows out of its own
 * source rather than appearing in a separate surface across the page.
 */
export default function OverviewScreen() {
  const { pageId } = usePageScope();
  // The window: 7/30/60, defaulting to 30 (why, measured, is on the pill
  // below). The query is hoisted to this level so the summary line can render
  // before any tab is open. It answers with the window *and the one before it*
  // — `getPerformanceWindow` sets out why that takes one doubled read.
  const [days, setDays] = useState(30);
  const { data, error, loading, refresh } = useQuery(
    () => getPerformanceWindow(pageId!, days),
    [pageId, days],
    { enabled: pageId !== null },
  );

  // Which tab is open, held here rather than left to `defaultValue`, because
  // the window pill beside the switcher belongs to Performance alone: 7/30/60
  // says nothing about the saved list, and left on screen over the Saved tab it
  // reads as that tab's control.
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
        className="flex min-h-0 flex-1 flex-col gap-3"
      >
        {/* The chrome: tab switcher, then the window pill. It is a translucent
            layer rather than an opaque strip — the rows fade out underneath it
            at the scroller's top edge (see `ScrollFade`) instead of meeting a
            hard bar. `-mr-3 pr-3` extends it across the scroller's right gutter
            so nothing bleeds through the gap.

            `backdrop-blur` is dropped entirely under `prefers-reduced-
            transparency`, where the surface goes solid instead. */}
        <div
          className={cn(
            "relative z-20 -mr-3 shrink-0 pr-3 pb-1",
            // `md` (12px), not `xl` (24px). A backdrop filter repaints
            // continuously while the table scrolls under it, the cost scales
            // with the radius, and Safari feels it worst. On a 40px strip the
            // extra 12px was not visible — it was only expensive.
            "bg-background/75 backdrop-blur-md backdrop-saturate-150",
            "[@media(prefers-reduced-transparency:reduce)]:bg-background [@media(prefers-reduced-transparency:reduce)]:backdrop-blur-none",
          )}
        >
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
                the app. Lives here, beside the tabs and above the list it
                filters, on the Performance tab only. */}
            {tab === "performance" ? (
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

        {/* A flex *column*, not a plain block. `ScrollFade` inside is
            `min-h-0 flex-1 overflow-y-auto`, and both of those size against a
            flex parent — without this the scroller had no height to be bounded
            by, grew to its content, and the page could not be scrolled at all
            past the tenth row. */}
        <TabsContent
          value="performance"
          className="flex min-h-0 flex-1 flex-col"
        >
          <Performance
            days={days}
            data={data}
            error={error}
            loading={loading}
            refresh={refresh}
          />
        </TabsContent>
        <TabsContent value="saved" className="flex min-h-0 flex-1 flex-col">
          <Saved />
        </TabsContent>
      </Tabs>
    </div>
  );
}

/**
 * A scroller whose top edge fades its content out, and only once scrolled.
 *
 * The alternative is a 1px divider under the chrome, or an opaque bar the rows
 * disappear behind — both read as two separate screens stacked. This is the
 * scroll edge effect: where content passes under floating chrome it dissolves,
 * and where there is nothing overlapping (scroll position 0) the mask is not
 * applied at all, so the first row is not permanently half-faded.
 *
 * The listener is `passive` and writes a boolean, not a scroll offset — the
 * mask is on or off, so re-rendering on every pixel would buy nothing.
 */
function ScrollFade({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [scrolled, setScrolled] = useState(false);

  const onScroll = useCallback(() => {
    const node = ref.current;
    if (node) setScrolled(node.scrollTop > 4);
  }, []);

  // Re-checked on mount because the content can arrive taller than the box
  // while the scroll position is restored from a previous render.
  useEffect(onScroll, [onScroll]);

  return (
    // **The scroller is not the layout box.** The caller's `flex flex-col`
    // used to land on this element, which made the table card a flex *item* of
    // the scroll container — and a flex item shrinks before it overflows. The
    // card was squeezed to the viewport, clipped its own last rows behind its
    // `overflow-hidden`, and `scrollHeight` stayed exactly equal to
    // `clientHeight`, so there was nothing to scroll and no way to reach row
    // ten. The caller's layout goes on an ordinary block inside instead, which
    // is free to grow and hand this element something to scroll.
    // `relative`, to hang the gradient off the top edge.
    <div className="relative flex min-h-0 flex-1 flex-col">
      <div
        ref={ref}
        onScroll={onScroll}
        className="min-h-0 flex-1 overflow-y-auto pr-3"
      >
        <div className={className}>{children}</div>
      </div>

      {/* **An overlay whose opacity animates, not a `mask-image` that snaps
          on.** The mask was the obvious implementation and it popped:
          `mask-image` interpolates between two gradients badly enough that
          nothing usable comes out of a transition, so the fade appeared in one
          frame the moment `scrollTop` passed 4px. Opacity on a separate layer
          is compositor-only and crosses in 150ms.

          `from-background` rather than a mask also means it dissolves content
          into the page's own ground, which is what the translucent chrome
          above it is sitting on. */}
      <div
        aria-hidden
        className={cn(
          "pointer-events-none absolute inset-x-0 top-0 h-5 bg-gradient-to-b from-background to-transparent",
          "transition-opacity duration-150 ease-out",
          scrolled ? "opacity-100" : "opacity-0",
        )}
      />
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
 * Two regions, not four:
 *
 * - **the summary line**: what the window adds up to, and whether that is up or
 *   down on the window before it, in one sentence of text;
 * - **the table**: the ranked list, with each row's engagement drawn as a bar
 *   against the window's best so the fall-off is visible without reading a
 *   single digit. A row opens in place to show the picture, the caption, the
 *   full breakdown and the actions.
 *
 * The detail used to live in a lead strip above the list. It moved into the row
 * because the strip repeated the row it was describing — the same five figures
 * twice, a hundred pixels apart — and because a panel that grows out of the row
 * you clicked says which post it belongs to without a rank badge to connect
 * them.
 */
function Performance({
  days,
  data,
  error,
  loading,
  refresh,
}: {
  days: number;
  data: PerformanceWindow | null;
  error: string | null;
  loading: boolean;
  refresh: () => void;
}) {
  const { pageId } = usePageScope();
  const [busy, setBusy] = useState<string | null>(null);
  // The *pagination* page. The Page is `pageId` — the same collision of names
  // the Review queue has, and named the same way.
  const [page, setPage] = useState(1);
  // Which row is open, or none. Nothing is expanded on arrival: the table is
  // the screen and it should read as a table until a post is asked about.
  const [openId, setOpenId] = useState<string | null>(null);
  // Reset the pager and any open row when the window changes: page 12 of a
  // 60-day window is nowhere in a 7-day one, and the clamp on its own would
  // land on that window's last page rather than its best posts. Done during
  // render, not in an effect — same reasoning as the page clamp below.
  const [lastDays, setLastDays] = useState(days);
  if (lastDays !== days) {
    setLastDays(days);
    setPage(1);
    setOpenId(null);
  }

  const posts = data?.posts ?? null;

  // Paged, like the queue, and for a sharper version of the queue's reason: 30
  // days is 219 posts on History Retraced and 60 is over 400.
  const total = posts?.length ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / QUEUE_PAGE_SIZE));
  const safePage = Math.min(page, totalPages);
  const shown = posts?.slice(
    (safePage - 1) * QUEUE_PAGE_SIZE,
    safePage * QUEUE_PAGE_SIZE,
  );

  // Clamped during render rather than in an effect — `review-list.tsx` sets out
  // why. Here it also covers the window shrinking under the stored page.
  if (page > totalPages) setPage(totalPages);

  // The bar scale is the window's best, not the page's: the sort is global, so
  // page two's bars have to be shorter than page one's or the bar is measuring
  // nothing. `posts[0]` is that maximum, the list already being sorted.
  const best = posts?.[0]?.engagement ?? 0;

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

  if (loading || !posts)
    return (
      <ScrollFade>
        <Loading label="Reading Metricool" className="h-64 rounded-xl border" />
      </ScrollFade>
    );

  if (posts.length === 0)
    return (
      <ScrollFade>
        <p className="rounded-xl border border-dashed p-10 text-center text-sm text-muted-foreground">
          Nothing published in this window.
        </p>
      </ScrollFade>
    );

  return (
    <ScrollFade className="flex flex-col gap-3">
      <Summary posts={posts} previous={data?.previous ?? []} days={days} />

      <div className="overflow-hidden rounded-xl border bg-card">
        <TableHead />
        <div className="flex flex-col">
          {shown?.map((post, index) => (
            <PostRow
              key={post.post_id}
              post={post}
              // Ranked across the whole window, not within the page: the sort
              // is global, so the first row of page two is 11.
              rank={(safePage - 1) * QUEUE_PAGE_SIZE + index + 1}
              share={best > 0 ? post.engagement / best : 0}
              open={openId === post.post_id}
              busy={busy === post.post_id}
              onToggle={() =>
                setOpenId((current) =>
                  current === post.post_id ? null : post.post_id,
                )
              }
              onSave={() => void keep(post)}
            />
          ))}
        </div>
        <QueuePagination
          totalItems={total}
          page={safePage}
          onPageChange={setPage}
        />
      </div>
    </ScrollFade>
  );
}

/**
 * What the window adds up to, in one line, and whether it is up or down.
 *
 * This was a bordered card of three cells. On screen it was a 1300px box
 * holding three six-character numbers, ninety pixels tall, directly above a
 * second card and a third — three framed surfaces stacked, where the frames
 * were doing work that spacing and type weight do better. It is now a sentence:
 * the figures carry weight, the words between them stay muted, and the whole
 * thing costs one line.
 *
 * **The comparison is the point.** "3.2M reach" is neither good nor bad on its
 * own; "up 12% on the previous 30 days" is a fact an operator can act on. The
 * previous window comes out of the same read (see `OverviewScreen`) and the
 * delta is on engagement, because engagement is what the list is sorted by and
 * three arrows on one line would be noise. It is absent, rather than shown as
 * zero, when there is no previous window to compare against — a Page in its
 * first month has nothing behind it, and "0%" would be a claim rather than an
 * absence.
 */
function Summary({
  posts,
  previous,
  days,
}: {
  posts: PostStats[];
  previous: PostStats[];
  days: number;
}) {
  const sum = (rows: PostStats[], key: "impressions" | "engagement") =>
    rows.reduce((running, row) => running + row[key], 0);

  const reach = sum(posts, "impressions");
  const engagement = sum(posts, "engagement");
  const was = sum(previous, "engagement");
  const delta = was > 0 ? (engagement - was) / was : null;
  const up = delta !== null && delta >= 0;

  return (
    <p className="flex flex-wrap items-center gap-x-2 gap-y-1 px-0.5 text-sm text-muted-foreground">
      <Figure value={metric(posts.length)} label="posts" />
      <span aria-hidden>·</span>
      <Figure value={metric(reach)} label="reach" />
      <span aria-hidden>·</span>
      <Figure value={metric(engagement)} label="engagement" />

      {delta === null ? null : (
        <span
          title={`${metric(was)} engagement over the ${days} days before this window.`}
          // The same chip whichever way it points, and the arrow is the only
          // thing that says which. A window that engaged less is not an error,
          // and `destructive` red on this screen already means Remove — a red
          // -41% read as something having gone wrong rather than as a quieter
          // month.
          className="inline-flex items-center gap-1 rounded-full bg-foreground/[0.06] px-2 py-0.5 text-xs font-medium text-foreground tabular-nums"
        >
          {up ? (
            <TrendingUp className="size-3" />
          ) : (
            <TrendingDown className="size-3" />
          )}
          {up ? "+" : ""}
          {Math.round(delta * 100)}%
          <span className="font-normal text-muted-foreground">
            vs prev {days}d
          </span>
        </span>
      )}
    </p>
  );
}

/** One figure of the summary line: the number carries the weight, the word does not. */
function Figure({ value, label }: { value: string; label: string }) {
  return (
    <span>
      {/* `tracking-tight` because the figure is set heavier and larger than the
          word beside it, and letters read too far apart as they grow. */}
      <strong className="font-semibold tracking-tight text-foreground tabular-nums">
        {value}
      </strong>{" "}
      {label}
    </span>
  );
}

/**
 * The table's column labels.
 *
 * `lg` only — the columns they name drop below it, where they would crowd the
 * headline. `aria-hidden` because the digits read fine without the labels in a
 * screen reader, which already gets them as part of a row's meaning.
 *
 * Every column that carries a number is named. The previous version left the
 * boldest figure in each row — engagement, the one the whole list is ordered
 * by — with no label at all, sitting between a column called REACH and an
 * unlabelled date.
 */
/**
 * The row's own gutters and column rhythm, shared by the header and every row
 * beneath it so the two cannot drift apart.
 *
 * **`gap-5`, not `gap-3`, and `px-5`, not `px-3`.** The first cut of the table
 * ran the four figure columns hard against each other and against the card's
 * edge; four numbers 12px apart read as one number with spaces in it, and the
 * rank sat almost on the border. The columns are what makes this a table, so
 * they need enough air to read as separate measures.
 */
const ROW_PADDING = "gap-5 px-5 py-3";

/** One right-aligned figure column. Fixed so the digits line up down the page. */
const NUMBER_COLUMN = "w-16 shrink-0 text-right";

/** A column label. Furniture, not data — mono, muted, and the same everywhere. */
const LABEL =
  "font-mono text-[10px] tracking-[0.12em] text-muted-foreground uppercase";

function TableHead() {
  return (
    <div
      aria-hidden
      className={cn("hidden items-center border-b bg-muted/30 lg:flex", ROW_PADDING)}
    >
      <span className="w-6 shrink-0" />
      <span className={cn("min-w-0 flex-1", LABEL)}>Post</span>
      <span className={cn(NUMBER_COLUMN, LABEL)}>Reac.</span>
      <span className={cn(NUMBER_COLUMN, LABEL)}>Com.</span>
      <span className={cn(NUMBER_COLUMN, LABEL)}>Shares</span>
      <span className={cn(NUMBER_COLUMN, "w-20", LABEL)}>Reach</span>
      <span className={cn("w-40 shrink-0 text-right", LABEL)}>Engagement</span>
      <span className={cn("w-24 shrink-0 text-right", LABEL)}>Published</span>
      <span className="w-4 shrink-0" />
    </div>
  );
}

/**
 * A row that opens in place.
 *
 * The shell both tables share: a button that is the whole row, and a panel
 * underneath it that grows out of it.
 *
 * **`grid-template-rows: 0fr → 1fr`, not a height.** The panel's height is not
 * known — a caption is one line or four — and animating to `auto` is not
 * something CSS can do. The grid track can, and it interpolates from whatever
 * value is on screen, so a row toggled mid-animation reverses from where it
 * actually is rather than jumping to the end of the outgoing one.
 *
 * The curve is the flat-in, long-tail one a spring settles with (no overshoot:
 * nothing here was thrown, it was clicked), mirrored between opening and
 * closing so the panel returns along the path it arrived on. Both are dropped
 * under `prefers-reduced-motion`, where the panel simply appears.
 */
function ExpandingRow({
  open,
  onToggle,
  summary,
  detail,
}: {
  open: boolean;
  onToggle: () => void;
  summary: React.ReactNode;
  detail: React.ReactNode;
}) {
  return (
    <div className={cn("border-b last:border-0", open && "bg-muted/25")}>
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        className={cn(
          "flex w-full items-center text-left outline-none",
          ROW_PADDING,
          // Colour only, and fast. The press has to land on pointer-down, which
          // is what `:active` is; anything waiting for the click reads as lag.
          // No `scale` on press, deliberately: a row is the full width of the
          // table and shrinking it reads as the table flexing, not as a button.
          //
          // **Plain `hover:` is already touch-safe here.** Tailwind v4 emits
          // every `hover:` utility inside `@media (hover: hover)`, so a tap on
          // a touch device does not leave the row lit. Hand-writing that media
          // query as an arbitrary variant is redundant, and the obvious
          // spelling of it is a build error — joining the two feature queries
          // without a space around `and` produces an at-rule PostCSS rejects,
          // and the *entire* stylesheet then fails to compile: every screen in
          // the app renders unstyled, not just this row.
          //
          // Do not paste that broken class here as an example. Tailwind's
          // scanner is a regex over the raw file, not a JS parser, so a class
          // name written inside a comment is still collected and still emitted.
          // The first version of this note re-created the exact bug it was
          // describing, and the build stayed broken until the prose changed.
          "transition-colors duration-100 hover:bg-muted/40 active:bg-muted/70",
          // Inset, not the browser default: the list's own `overflow-hidden`
          // clips an outset ring to a sliver on whichever edge touches the
          // card, so a keyboard user tabbing the table sees almost nothing.
          "focus-visible:ring-ring/50 focus-visible:ring-2 focus-visible:ring-inset",
        )}
      >
        {summary}
        <ChevronRight
          aria-hidden
          className={cn(
            "size-4 shrink-0 text-muted-foreground",
            // 200ms: it is a 16px glyph, and the small-element band is
            // 125–200. It still reads as turning with the panel because both
            // ride the same curve.
            "transition-transform duration-200 ease-[cubic-bezier(0.32,0.72,0,1)] motion-reduce:transition-none",
            open && "rotate-90",
          )}
        />
      </button>

      {/* **Closing is faster than opening.** Opening is the answer to a
          question and can take its time; closing is the system getting out of
          the way, and 300ms of that reads as the row being reluctant. The curve
          is Ionic's drawer easing, mirrored across both directions so the panel
          returns along the path it arrived on. */}
      <div
        className={cn(
          "grid transition-[grid-template-rows] ease-[cubic-bezier(0.32,0.72,0,1)] motion-reduce:transition-none",
          open ? "grid-rows-[1fr] duration-300" : "grid-rows-[0fr] duration-200",
        )}
      >
        {/* The clip. The grid track goes to zero; this is what hides the
            content while it does.

            **`inert` while closed, and it is not decoration.** `overflow-
            hidden` clips the panel to nothing on screen but leaves its buttons
            in the document at full size — Playwright found this by resolving a
            collapsed row's Save button as visible and then failing to click it,
            because the row's own button was what actually sat at those
            coordinates. A keyboard user would have hit the same thing without
            the error message: ten rows of invisible Open/Save/Repost/Remove
            between one headline and the next. `inert` takes the whole subtree
            out of the tab order, out of hit testing and out of the
            accessibility tree, which is all three problems at once. */}
        <div className="overflow-hidden" inert={!open}>
          {/* A short lift as it arrives, so the panel reads as coming out of
              the row rather than being revealed behind it. Delayed on the way
              in and not on the way out, which is the asymmetry that keeps the
              close feeling immediate. */}
          {/* Reduced motion keeps the fade and drops the travel. `transition-
              none` here was over-correcting: a cross-fade is what the setting
              asks you to fall back *to*, and killing it left the panel's
              contents snapping in at full opacity. Only the 4px lift is
              vestibular, so only the 4px lift goes. */}
          <div
            className={cn(
              "transition-[opacity,translate] duration-200 ease-out",
              "motion-reduce:translate-y-0 motion-reduce:transition-[opacity]",
              open ? "translate-y-0 opacity-100 delay-75" : "-translate-y-1 opacity-0",
            )}
          >
            {detail}
          </div>
        </div>
      </div>
    </div>
  );
}

/**
 * One row of the ranked list.
 *
 * Rank, headline, the four numbers, then engagement drawn as a bar beside its
 * own figure. **The bar is the change that matters here.** A column reading
 * 7.2K / 7.1K / 6.3K / 5K / 4.4K makes the reader parse five numbers to see a
 * shape; the bars show the fall-off at a glance and cost no vertical space. It
 * sits immediately left of the figure it encodes rather than out at the start
 * of the row, because a measure and its scale belong next to each other — put
 * the bar by the headline and the eye has to travel the width of the table to
 * find out what it is measuring.
 *
 * The 36px thumbnail is gone. At that size the composite — dark photograph with
 * small painted text — is a grey smudge that identifies nothing; the headline
 * does that work. The picture is in the panel below, at the size it was made
 * for.
 */
function PostRow({
  post,
  rank,
  share,
  open,
  busy,
  onToggle,
  onSave,
}: {
  post: PostStats;
  rank: number;
  /** This post's engagement as a fraction of the window's best. */
  share: number;
  open: boolean;
  busy: boolean;
  onToggle: () => void;
  onSave: () => void;
}) {
  const column = cn(
    NUMBER_COLUMN,
    "hidden font-mono text-[11px] text-muted-foreground tabular-nums lg:block",
  );

  return (
    <ExpandingRow
      open={open}
      onToggle={onToggle}
      summary={
        <>
          {/* Rank, not a bullet: the list is sorted, so its position is
              information. The top three read in gold, the one warm accent the
              app owns — it is the same yellow painted into the published
              images, so "top of the Page" and "the post itself" share one
              colour. */}
          <span
            className={cn(
              "w-6 shrink-0 text-right font-mono text-xs tabular-nums",
              rank <= 3 ? "font-semibold text-gold" : "text-muted-foreground",
            )}
          >
            {rank}
          </span>

          {/* The headline, not the whole caption — the caption is the headline
              and the recap run together, and truncating that names nothing.
              Same treatment the Review queue gives a draft, same helper. */}
          <span className="min-w-0 flex-1 truncate text-sm font-medium">
            {headline(post.text) || "(no text)"}
          </span>

          <span className={column}>{metric(post.reactions)}</span>
          <span className={column}>{metric(post.comments)}</span>
          <span className={column}>{metric(post.shares)}</span>
          <span className={cn(column, "w-20")}>{metric(post.impressions)}</span>

          {/* The bar and its figure as one cell, matching the header's `w-40`.
              The bar is neutral rather than gold: the *length* carries the
              meaning here, and gold already means two other things on this
              screen. 96px and a fill at 60% — the first cut was 64px at 35%,
              which on screen was a pale dash whose whole dynamic range across a
              page was about twenty pixels. */}
          <span className="flex w-40 shrink-0 items-center justify-end gap-3">
            <span
              aria-hidden
              className="hidden h-1.5 w-24 rounded-full bg-foreground/10 sm:block"
            >
              {/* **Clipped, not resized.** The fill is always full width and
                  `clip-path` eats it back from the right. Animating `width`
                  here re-ran layout and paint on every frame for ten bars at
                  once, which is the one thing not to animate; `clip-path` is
                  composited.

                  `scaleX` would also be composited and is the usual answer, but
                  it squashes the pill's end caps into ellipses at short
                  lengths. `inset(… round 9999px)` re-rounds the cap *at the
                  clip edge* instead, so a 20% bar has the same end as a 100%
                  one.

                  300ms, down from 500: the window pill re-scales every bar at
                  once and showing that the column moved does not need half a
                  second. */}
              <span
                className={cn(
                  "block h-full w-full rounded-full bg-foreground/60",
                  "transition-[clip-path] duration-300 ease-out motion-reduce:transition-none",
                )}
                style={{
                  clipPath: `inset(0 ${(1 - Math.max(share, 0.02)) * 100}% 0 0 round 9999px)`,
                }}
              />
            </span>
            <span className="text-sm font-semibold tabular-nums">
              {metric(post.engagement)}
            </span>
          </span>

          <span className="hidden w-24 shrink-0 text-right font-mono text-[11px] text-muted-foreground sm:block">
            {timeAgo(post.published_at)}
          </span>
        </>
      }
      detail={
        <PostDetail
          text={post.text}
          picture={post.picture_url}
          publishedAt={post.published_at}
          stats={post}
          // px-5 + the rank column's w-6 + gap-5 = 64px.
          indent="sm:pl-16"
          actions={
            <>
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
                disabled={busy || post.saved}
                title={post.saved ? "Already saved" : "Keep this post for reference"}
              >
                {busy ? (
                  <Loader2 className="size-3.5 animate-spin [animation-duration:600ms]" />
                ) : post.saved ? (
                  <BookmarkCheck className="size-3.5" />
                ) : (
                  <Bookmark className="size-3.5" />
                )}
                {post.saved ? "Saved" : "Save"}
              </Button>
            </>
          }
        />
      }
    />
  );
}

/**
 * The panel under an opened row: the picture, the caption, the breakdown, the
 * actions.
 *
 * Shared by both tables — a saved post and a live one differ in their numbers'
 * provenance and in what you can do with them, not in how they read.
 *
 * **The breakdown is a line of text, not a row of tiles.** The tiles were a
 * bordered grid inside a bordered card inside a bordered list; three frames
 * deep, and each tile held four characters in a box wide enough for twenty. The
 * numbers are set heavier than their labels and that is the whole hierarchy
 * they need.
 */
function PostDetail({
  text,
  picture,
  publishedAt,
  stats,
  indent,
  meta,
  actions,
  statsHint,
}: {
  text: string;
  picture: string | null;
  publishedAt: string | null;
  stats: { reactions: number; comments: number; shares: number; impressions: number };
  /**
   * Left indent that lands the panel under its row's headline.
   *
   * It is a prop rather than a constant because the two tables start their
   * headline in different places: the ranked one has a rank column in front of
   * it, the saved one does not, and a single value left the saved panel
   * indented for a column that is not there.
   */
  indent: string;
  /** Replaces the default "published ..." line, for a saved post's two dates. */
  meta?: React.ReactNode;
  actions: React.ReactNode;
  statsHint?: string;
}) {
  return (
    // `indent` lands the picture on the same left edge as its row's headline,
    // so the panel reads as belonging to the row rather than as a block that
    // happens to follow it.
    //
    // Generous on every other side, and deliberately more than the rows get. A
    // row is one line in a table and wants to be scannable; the open panel is
    // the one place on this screen you stop and read, and it was cramped
    // against the row above it and the row below.
    <div
      className={cn(
        "flex flex-col gap-5 px-5 pt-2 pb-7 sm:flex-row sm:gap-6 sm:pt-3 sm:pr-8 sm:pb-8",
        indent,
      )}
    >
      {/* The picture at the size it exists at. Measured 2026-08-18 on History
          Retraced: the file the CDN serves is 130x163 and there is no other —
          Metricool's `fullPicture` is null on every row and the signed URL
          answers 403 to any edit of its `stp` size directive. So the column is
          112px, comfortably under native, and never a hero. */}
      <Thumbnail src={picture} className="w-24 sm:w-28" />

      <div className="min-w-0 flex-1 space-y-4">
        {/* **The caption from the top, not a headline and then a recap.** The
            panel used to repeat the row's headline as its own heading, which
            for a short title was the same words twice thirty pixels apart. The
            whole caption instead resolves the row's truncation — the first
            sentence is where the row's "…" cut off — and reads as one piece of
            prose rather than a title bar over a body. Four lines, because the
            rest is one click away on Open. */}
        {/* `max-w-prose` because the panel is as wide as the table and the
            table is very wide. Left to fill it, the caption ran about 1080px —
            roughly 170 characters a line, far past the point where the eye
            reliably finds the start of the next one. */}
        <p className="line-clamp-6 max-w-prose text-[13px] leading-relaxed text-muted-foreground">
          {text.trim() || "No caption."}
        </p>

        {/* **`lg:hidden`. The row's own columns carry these above `lg`**, lined
            up down the table where they can be compared between posts, and
            printing them again here would be the lead strip's mistake in a
            smaller box. Below `lg` those columns are gone and this is the only
            place the breakdown exists. */}
        <p className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground lg:hidden">
          <Breakdown value={stats.reactions} label="reactions" />
          <Breakdown value={stats.comments} label="comments" />
          <Breakdown value={stats.shares} label="shares" />
          <Breakdown value={stats.impressions} label="reach" />
        </p>

        <div className="flex flex-wrap items-center gap-2">
          {actions}
          <span className="ml-auto text-[11px] text-muted-foreground">
            {meta ?? (
              <span title={fullDate(publishedAt)}>
                Published {timeAgo(publishedAt)}
              </span>
            )}
          </span>
        </div>

        {/* Said out loud rather than left as a tooltip. The breakdown it
            qualifies is `lg:hidden`, so hanging the caveat on that element's
            `title` hid it exactly where the numbers are most visible — and a
            saved post's figures being frozen is the one thing about this tab
            that is not guessable from looking at it. */}
        {statsHint ? (
          <p className="text-[11px] text-muted-foreground">{statsHint}</p>
        ) : null}
      </div>
    </div>
  );
}

function Breakdown({ value, label }: { value: number; label: string }) {
  return (
    <span>
      <strong className="font-semibold text-foreground tabular-nums">
        {metric(value)}
      </strong>{" "}
      {label}
    </span>
  );
}

/**
 * The post's picture, or a stand-in.
 *
 * Facebook's CDN URLs are signed and expire — the same trap the competitor
 * pictures document — so a missing thumbnail is the expected end state rather
 * than a fault. The row carries its numbers either way.
 *
 * **4:5 is measured rather than chosen.** The composite is 4:5, so that is the
 * box shape: `object-cover` on a square cut the top and bottom off every
 * thumbnail — exactly where the hook text is painted.
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
        "aspect-4/5 shrink-0 rounded-xl border bg-muted object-cover",
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
  // Which row is open, or none — the Performance table's twin.
  const [openId, setOpenId] = useState<number | null>(null);

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
    return (
      <ScrollFade>
        <Loading label="Loading saved posts" className="h-64 rounded-xl border" />
      </ScrollFade>
    );

  if (data.length === 0)
    return (
      <ScrollFade>
        <p className="rounded-xl border border-dashed p-10 text-center text-sm text-muted-foreground">
          Nothing saved yet. Keep a post from Performance and it stays here.
        </p>
      </ScrollFade>
    );

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

  return (
    // No standing paragraph above the list. It explained Repost and Write
    // again, which are two labelled buttons carrying that same sentence as
    // their tooltip, and warned that the stats are a snapshot — now the tooltip
    // on the breakdown line that the warning is about.
    <ScrollFade className="flex flex-col gap-3">
      <div className="overflow-hidden rounded-xl border bg-card">
        {/* No rank and no engagement column: saved posts are ordered by when
            they were kept, not by how they did, so a bar here would rank a list
            that is not a ranking. */}
        <div
          aria-hidden
          className={cn("hidden items-center border-b bg-muted/30 lg:flex", ROW_PADDING)}
        >
          <span className={cn("min-w-0 flex-1", LABEL)}>Post</span>
          <span className={cn(NUMBER_COLUMN, LABEL)}>Reac.</span>
          <span className={cn(NUMBER_COLUMN, LABEL)}>Com.</span>
          <span className={cn(NUMBER_COLUMN, LABEL)}>Shares</span>
          <span className={cn(NUMBER_COLUMN, "w-20", LABEL)}>Reach</span>
          <span className={cn("w-24 shrink-0 text-right", LABEL)}>Last posted</span>
          <span className="w-4 shrink-0" />
        </div>

        <div className="flex flex-col">
          {shown.map((saved) => (
            <SavedRow
              key={saved.id}
              saved={saved}
              open={openId === saved.id}
              busy={busy === saved.id}
              onToggle={() =>
                setOpenId((current) => (current === saved.id ? null : saved.id))
              }
              onRepost={() => void repost(saved)}
              onReuse={() => void reuse(saved)}
              onRemove={() => void drop(saved)}
            />
          ))}
        </div>
        <QueuePagination
          totalItems={data.length}
          page={safePage}
          onPageChange={setPage}
        />
      </div>
    </ScrollFade>
  );
}

/**
 * A row of the saved table — the Performance row without its ranking, since
 * this list is ordered by when a post was kept rather than by how it did.
 */
function SavedRow({
  saved,
  open,
  busy,
  onToggle,
  onRepost,
  onReuse,
  onRemove,
}: {
  saved: SavedPost;
  open: boolean;
  busy: boolean;
  onToggle: () => void;
  onRepost: () => void;
  onReuse: () => void;
  onRemove: () => void;
}) {
  const column = cn(
    NUMBER_COLUMN,
    "hidden font-mono text-[11px] text-muted-foreground tabular-nums lg:block",
  );

  return (
    <ExpandingRow
      open={open}
      onToggle={onToggle}
      summary={
        <>
          <span className="min-w-0 flex-1 truncate text-sm font-medium">
            {headline(saved.text) || "(no text)"}
          </span>
          <span className={column}>{metric(saved.reactions)}</span>
          <span className={column}>{metric(saved.comments)}</span>
          <span className={column}>{metric(saved.shares)}</span>
          <span className={cn(column, "w-16")}>{metric(saved.impressions)}</span>
          {/* The client's ask: "there needs to be a visible date showing how
              many days ago it was posted last." Relative, because that is the
              question — whether it is far enough back to run again — and the
              exact stamp is in the panel below rather than a second line nobody
              reads. */}
          <span
            className="w-24 shrink-0 text-right font-mono text-[11px] text-muted-foreground"
            title={fullDate(saved.published_at)}
          >
            {timeAgo(saved.published_at)}
          </span>
        </>
      }
      detail={
        <PostDetail
          text={saved.text}
          picture={saved.picture_url}
          publishedAt={saved.published_at}
          stats={saved}
          // No rank column here, so the headline starts at the gutter.
          indent="sm:pl-5"
          statsHint="What the post had scored when it was saved, not a live figure."
          meta={
            <>
              Saved{" "}
              <span title={fullDate(saved.created_at)}>{timeAgo(saved.created_at)}</span>
              {" · last posted "}
              <span title={fullDate(saved.published_at)}>
                {timeAgo(saved.published_at)}
              </span>
            </>
          }
          actions={
            <>
              <Button
                variant="default"
                size="sm"
                disabled={busy}
                onClick={onRepost}
                title="Queue the original again — same caption, same picture. It lands in Review to publish."
              >
                {busy ? (
                  <Loader2 className="size-3.5 animate-spin [animation-duration:600ms]" />
                ) : (
                  <Repeat2 className="size-3.5" />
                )}
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
                className="text-destructive hover:bg-destructive/10 hover:text-destructive"
                title="Stop keeping this post"
              >
                <BookmarkCheck className="size-3.5" />
                Remove
              </Button>
            </>
          }
        />
      }
    />
  );
}
