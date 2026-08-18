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
  // The *pagination* page. The Page is `pageId` — the same collision of names
  // the Review queue has, and named the same way.
  const [page, setPage] = useState(1);

  const { data, error, loading, refresh } = useQuery(
    () => getPerformance(pageId!, days),
    [pageId, days],
    { enabled: pageId !== null },
  );

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
        <Tabs
          value={String(days)}
          onValueChange={(next) => {
            setDays(Number(next));
            // Back to page 1: page 12 of a 60-day window is nowhere in a 7-day
            // one, and the clamp on its own would land on that window's last
            // page rather than its best posts.
            setPage(1);
          }}
        >
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
        <Loading label="Reading Metricool" className="h-64 rounded-lg border" />
      ) : data.length === 0 ? (
        <p className="rounded-lg border border-dashed p-10 text-center text-sm text-muted-foreground">
          Nothing published in this window.
        </p>
      ) : (
        <>
          <Totals posts={data} days={days} />
          <div className="overflow-hidden rounded-lg border bg-card">
            {/* The rows keep their own box so `last:border-0` still finds a
                last row. Hung directly off the outer element, the pager became
                the last child and every row kept a rule that then doubled up
                against the pager's own. */}
            <div className="px-2">
              {shown?.map((post, index) => (
                <PostRow
                  key={post.post_id}
                  post={post}
                  // Ranked across the whole window, not within the page: the
                  // sort is global, so the first row of page two is 11.
                  rank={(safePage - 1) * QUEUE_PAGE_SIZE + index + 1}
                  busy={busy === post.post_id}
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
    // `items-stretch`, not `items-center`. The poster is 140px and the text was
    // two short lines floating in the middle of it — the row was as tall as its
    // image and filled by nothing. Stretched, the middle column can put its
    // title at the top and its figures at the bottom, so the height the picture
    // costs is height the row uses.
    <div className="group flex items-stretch gap-4 border-b px-2 py-3 transition-colors last:border-0 hover:bg-muted/40">
      {/* Rank, not a bullet: the list is sorted, so its position is
          information. Mono and muted — it names the row, it is not a measure. */}
      <span className="w-6 shrink-0 pt-0.5 text-right font-mono text-[11px] text-muted-foreground">
        {rank}
      </span>

      <Thumbnail src={post.picture_url} />

      <div className="flex min-w-0 flex-1 flex-col">
        {/* The headline, not the whole caption — the caption is the headline and
            the recap run together, and truncating that names nothing. Same
            treatment the Review queue gives a draft, same helper. */}
        <p className="truncate text-sm font-medium">
          {headline(post.text) || "(no text)"}
        </p>

        {/* And the recap under it, which is what the row's spare height is for.
            Two lines: enough to tell two posts on the same subject apart, and
            `line-clamp` rather than `truncate` because this is prose being
            sampled rather than a label being shortened. */}
        <p className="line-clamp-2 pt-1.5 text-[13px] leading-relaxed text-muted-foreground">
          {body(post.text)}
        </p>

        <p className="mt-auto flex flex-wrap items-center gap-x-2 pt-2 font-mono text-[11px] text-muted-foreground">
          <span>{metric(post.reactions)} reactions</span>
          <span aria-hidden>·</span>
          <span>{metric(post.comments)} comments</span>
          <span aria-hidden>·</span>
          <span>{metric(post.shares)} shares</span>
          <span aria-hidden>·</span>
          <span>{metric(post.impressions)} reach</span>
        </p>
      </div>

      {/* One right-hand column, not two: the figure the list is ordered by, the
          date, and then the two things you can do to the row, stacked under
          them. The actions used to be a column of their own, which put them at
          a different x on every row width and left the corner they now occupy
          empty. `tabular-nums` here and not on the tiles — this is a column
          that has to align down forty rows, which is what tabular is for. */}
      <div className="flex shrink-0 flex-col items-end text-right">
        <p className="text-base font-semibold tabular-nums">
          {metric(post.engagement)}
        </p>
        <p className="font-mono text-[11px] text-muted-foreground">
          {timeAgo(post.published_at)}
        </p>

        {/* `mt-auto` drops these to the foot of the column, opposite the
            metrics line on the left, rather than tucking them under the date —
            the figures belong to the top line, the actions to the bottom one.
            `-mr-1.5` pulls the icon buttons' own padding back off the edge so
            the glyphs line up with the digits above. */}
        <div className="-mr-1.5 mt-auto flex items-center gap-0.5 pt-2">
          {post.permalink_url ? (
            <a
              href={post.permalink_url}
              target="_blank"
              rel="noreferrer"
              title="Open on Facebook"
              className="rounded p-1.5 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100 hover:text-foreground focus-visible:opacity-100"
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
 * **4:5 and 112px, both measured rather than chosen.** Measured 2026-08-18 on
 * History Retraced's 30-day window:
 *
 * - the file the CDN serves is **130 x 163**, and that is the only file there
 *   is. Metricool's `fullPicture` is null on every row, and the URL is signed
 *   (`oh`/`oe`), so editing its `stp=dst-jpg_p130x130` size directive to
 *   `p720x720`, or dropping `stp` altogether, both answer 403. Our own bucket
 *   holds full-resolution copies of what *we* published, and they are no help
 *   here either: of 20 drafts carrying a Metricool post id, 0 appear among the
 *   213 stats rows. So 112px is the widest this can be drawn and stay sharp;
 * - it was `aspect-square`, and the composite is 4:5. `object-cover` was
 *   therefore cutting the top and bottom off every thumbnail — which is exactly
 *   where the hook text is painted. The middle band of a poster is the part
 *   that identifies it least. `aspect-[4/5]` is also what the Review queue's
 *   thumbnail already uses.
 */
function Thumbnail({ src }: { src: string | null }) {
  if (!src) {
    return (
      <div className="flex aspect-4/5 w-28 shrink-0 items-center justify-center rounded-lg border bg-muted">
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
      className="aspect-4/5 w-28 shrink-0 rounded-lg border object-cover"
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
  // The pagination page, as in Performance and the Review queue.
  const [page, setPage] = useState(1);

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
    return <Loading label="Loading saved posts" className="h-64 rounded-lg border" />;

  if (data.length === 0) {
    return (
      <p className="rounded-lg border border-dashed p-10 text-center text-sm text-muted-foreground">
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

  return (
    <div className="space-y-3">
      <p className="text-xs text-muted-foreground">
        The numbers below are what each post had scored when it was saved, not a
        live figure. <strong className="font-medium text-foreground">Repost</strong>{" "}
        queues the original caption and picture; <strong className="font-medium text-foreground">Write again</strong>{" "}
        sends the story back through the writer for a fresh one.
      </p>

      <div className="overflow-hidden rounded-lg border bg-card">
        {/* The rows keep their own box so `last:border-0` still finds a last
            row — see the same note in Performance. */}
        <div className="px-2">
          {shown.map((saved) => (
            <div
              key={saved.id}
              className="group flex items-stretch gap-4 border-b px-2 py-3 transition-colors last:border-0 hover:bg-muted/40"
            >
              <Thumbnail src={saved.picture_url} />

              {/* Headline, recap, figures — the Performance row's shape, and it
                  earns its place here twice over: this is the tab where you
                  decide whether to run a story again, and the recap is what
                  that decision is about. */}
              <div className="flex min-w-0 flex-1 flex-col">
                <p className="truncate text-sm font-medium">
                  {headline(saved.text) || "(no text)"}
                </p>
                <p className="line-clamp-2 pt-1.5 text-[13px] leading-relaxed text-muted-foreground">
                  {body(saved.text)}
                </p>
                <p className="mt-auto flex flex-wrap items-center gap-x-2 pt-2 font-mono text-[11px] text-muted-foreground">
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
              <div className="flex shrink-0 flex-col items-end text-right">
                <div className="hidden sm:block">
                  <p className="text-sm font-medium" title={fullDate(saved.published_at)}>
                    {timeAgo(saved.published_at)}
                  </p>
                  <p className="font-mono text-[11px] text-muted-foreground">
                    last posted
                  </p>
                </div>

                {/* At the foot of the column, as on Performance: date at the
                    top, what you can do about it at the bottom. */}
                <div className="-mr-1.5 mt-auto flex items-center gap-1 pt-2">
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
                      className="rounded p-1.5 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100 hover:text-foreground focus-visible:opacity-100"
                    >
                      <ExternalLink className="size-3.5" />
                    </a>
                  ) : null}
                  <button
                    type="button"
                    onClick={() => void drop(saved)}
                    aria-label="Remove from saved"
                    title="Stop keeping this post"
                    className="rounded p-1.5 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100 hover:bg-destructive/10 hover:text-destructive focus-visible:opacity-100"
                  >
                    <BookmarkCheck className="size-4" />
                  </button>
                </div>
              </div>
            </div>
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
