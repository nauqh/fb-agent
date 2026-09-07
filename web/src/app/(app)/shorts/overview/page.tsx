"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ChevronRight, ExternalLink, Film, Play, RectangleHorizontal } from "lucide-react";

import { Loading } from "@/components/loading";
import { QueryError } from "@/components/query-error";
import { ScreenHeader } from "@/components/screen";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  NativeSelect,
  NativeSelectOption,
} from "@/components/ui/native-select";
import {
  listYoutubeBrands,
  getYoutubeOverview,
  type YoutubeBrand,
  type YoutubeOverview,
  type YoutubeVideo,
} from "@/lib/api/youtube";
import { fullDate, metric, timeAgo } from "@/lib/format";
import { useQuery } from "@/lib/use-query";
import { cn } from "@/lib/utils";

/**
 * How a channel's videos did — the Shorts workspace's Overview.
 *
 * The same three-part skeleton as the Facebook Overview — translucent chrome
 * with a scroll fade, a one-line summary with a comparison, and a ranked table
 * whose rows open in place — with the point of view changed for what YouTube
 * actually reports:
 *
 * - **Views are the rank, not engagement.** These channels draw near-zero
 *   likes/comments/shares (0–13 on real rows) while views span orders of
 *   magnitude; ranking by engagement would sort noise. So the bar measures
 *   views, and engagement rides as secondary figures in the panel.
 * - **The thumbnail is real.** Facebook's composite thumbnails are smudges at
 *   row size and were dropped; an i.ytimg.com frame is a real picture and
 *   identifies the video, so it earns the row.
 * - **Avg watch is the retention signal.** Views say how many clicked;
 *   seconds watched say whether they stayed. It is a YouTube-only measure and
 *   the honest companion to a view count.
 *
 * The day pills include **All**. A channel's catalog is a bounded set (80
 * videos on Bible Focus), not a stream like a Page's posts, so the overview's
 * default is everything; windows narrow from there, and only a window has a
 * `previous` to compare against.
 */
export default function YoutubeOverviewScreen() {
  const { data: brands, error: brandsError, loading: brandsLoading, refresh: refreshBrands } =
    useQuery(() => listYoutubeBrands(), []);

  // The brand the overview is about. Defaults to the first youtube-connected
  // profile; the picker only appears once there is more than one, which is the
  // same "a switch with a single position is decoration" rule the Page switcher
  // lives by.
  const [brandId, setBrandId] = useState<string>("");
  const selectedBrand =
    brands?.find((brand) => brand.id === brandId) ?? brands?.[0] ?? null;

  // All / 7 / 30 / 60. All is 0 and is the default — the catalog is bounded,
  // and windows on a dormant channel are empty.
  const [days, setDays] = useState(0);
  const { data, error, loading, refresh } = useQuery(
    () => getYoutubeOverview(selectedBrand!.id, days),
    [selectedBrand?.id, days],
    { enabled: !!selectedBrand },
  );

  // Keep `days` sticky when the brand changes, but land on the first brand
  // automatically when the list arrives (a picker with nothing selected would
  // read as broken).
  if (brands && !brandId && brands[0]) setBrandId(brands[0].id);

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <ScreenHeader
        title="Overview"
        hint="How the channel's videos did."
        switcher={false}
      />

      {/* The brand + window chrome. A translucent layer rather than an
          opaque strip — rows fade out beneath it at the scroller's top edge
          (see `ScrollFade`) instead of meeting a hard bar. `md` blur, not
          `xl`: a backdrop filter repaints continuously while the table
          scrolls under it and the cost scales with the radius. */}
      <div
        className={cn(
          "relative z-20 -mr-3 shrink-0 pr-3 pb-1",
          "bg-background/75 backdrop-blur-md backdrop-saturate-150",
          "[@media(prefers-reduced-transparency:reduce)]:bg-background [@media(prefers-reduced-transparency:reduce)]:backdrop-blur-none",
        )}
      >
        {brandsLoading || !brands ? (
          <div className="h-9" />
        ) : (
          <div className="flex flex-wrap items-center gap-3">
            {/* The brand scope control. Hidden below one brand, and a native
                select rather than a fancy dropdown because it is a scope
                control over fixed options — the Page switcher's reasoning. */}
            {(brands ?? []).length > 1 ? (
              <NativeSelect
                value={selectedBrand?.id ?? ""}
                onValueChange={setBrandId}
                ariaLabel="Channel"
                className="w-48"
              >
                {brands.map((brand) => (
                  <NativeSelectOption key={brand.id} value={brand.id}>
                    {brand.label}
                  </NativeSelectOption>
                ))}
              </NativeSelect>
            ) : null}

            <Tabs value={String(days)} onValueChange={(next) => setDays(Number(next))}>
              <TabsList className="w-fit shrink-0">
                <TabsTrigger value="0">All</TabsTrigger>
                <TabsTrigger value="7">7d</TabsTrigger>
                <TabsTrigger value="30">30d</TabsTrigger>
                <TabsTrigger value="60">60d</TabsTrigger>
              </TabsList>
            </Tabs>
          </div>
        )}
      </div>

      {brandsError ? (
        <QueryError error={brandsError} onRetry={refreshBrands} />
      ) : (
        <VideoTable
          selectedBrand={selectedBrand}
          data={data}
          loading={loading}
          error={error}
          days={days}
          refresh={refresh}
        />
      )}
    </div>
  );
}

/**
 * A scroller whose top edge fades its content out — the Overview's chrome
 * layer is translucent, and where content passes under it it dissolves rather
 * than meeting a hard bar. The mask is opacity on a layer (compositor-only)
 * rather than a `mask-image` that snaps.
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

  useEffect(onScroll, [onScroll]);

  return (
    <div className="relative flex min-h-0 flex-1 flex-col">
      <div
        ref={ref}
        onScroll={onScroll}
        className="min-h-0 flex-1 overflow-y-auto pr-3"
      >
        <div className={className}>{children}</div>
      </div>
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
 * The summary line and the ranked table.
 *
 * **The summary is one line, not a band.** The Facebook overview proved a
 * totals card costs ~500px before the first post for three numbers; the
 * figures carry weight, the words between them stay muted, and the comparison
 * delta is the part an operator can act on. Only a windowed read has a
 * `previous` — the whole catalog has nothing behind it, so the delta is
 * absent rather than shown as zero.
 */
function VideoTable({
  selectedBrand,
  data,
  loading,
  error,
  days,
  refresh,
}: {
  selectedBrand: YoutubeBrand | null;
  data: YoutubeOverview | null;
  loading: boolean;
  error: string | null;
  days: number;
  refresh: () => void;
}) {
  const [openId, setOpenId] = useState<string | null>(null);
  const videos = data?.posts ?? null;

  // Reset the open row when the brand or window changes: a row from another
  // channel is nowhere in this table, and the panel is about a specific video.
  const [lastKey, setLastKey] = useState<string>("");
  const key = `${selectedBrand?.id ?? ""}:${days}`;
  if (key !== lastKey) {
    setLastKey(key);
    setOpenId(null);
  }

  if (error) return <QueryError error={error} onRetry={refresh} />;

  if (loading || !videos)
    return (
      <ScrollFade>
        <Loading label="Reading Metricool" className="h-64 rounded-xl border" />
      </ScrollFade>
    );

  if (videos.length === 0)
    return (
      <ScrollFade>
        <p className="rounded-xl border border-dashed p-10 text-center text-sm text-muted-foreground">
          Nothing published in this window.
        </p>
      </ScrollFade>
    );

  const best = videos[0]?.views ?? 0;

  return (
    <ScrollFade className="flex flex-col gap-3">
      <Summary posts={videos} previous={data?.previous ?? []} days={days} />

      <div className="overflow-hidden rounded-xl border bg-card">
        <div
          aria-hidden
          className="hidden items-center border-b bg-muted/30 gap-5 px-5 py-3 lg:flex"
        >
          <span className="w-6 shrink-0" />
          <span className="w-24 shrink-0" />
          <span className="min-w-0 flex-1 font-mono text-[10px] tracking-[0.12em] text-muted-foreground uppercase">
            Video
          </span>
          <span className="w-16 shrink-0 text-right font-mono text-[10px] tracking-[0.12em] text-muted-foreground uppercase">
            Watch
          </span>
          <span className="w-32 shrink-0 text-right font-mono text-[10px] tracking-[0.12em] text-muted-foreground uppercase">
            Views
          </span>
          <span className="w-24 shrink-0 text-right font-mono text-[10px] tracking-[0.12em] text-muted-foreground uppercase">
            Published
          </span>
          <span className="w-4 shrink-0" />
        </div>

        <div className="flex flex-col">
          {videos.map((video, index) => (
            <VideoRow
              key={video.video_id}
              video={video}
              rank={index + 1}
              share={best > 0 ? video.views / best : 0}
              open={openId === video.video_id}
              onToggle={() =>
                setOpenId((current) =>
                  current === video.video_id ? null : video.video_id,
                )
              }
            />
          ))}
        </div>
      </div>
    </ScrollFade>
  );
}

/** What the window adds up to, in one line, and whether it is up or down. */
function Summary({
  posts,
  previous,
  days,
}: {
  posts: YoutubeVideo[];
  previous: YoutubeVideo[];
  days: number;
}) {
  const views = posts.reduce((running, video) => running + video.views, 0);
  const was = previous.reduce((running, video) => running + video.views, 0);
  const delta = was > 0 ? (views - was) / was : null;
  const up = delta !== null && delta >= 0;

  return (
    <p className="flex flex-wrap items-center gap-x-2 gap-y-1 px-0.5 text-sm text-muted-foreground">
      <Figure value={metric(posts.length)} label="videos" />
      <span aria-hidden>·</span>
      <Figure value={metric(views)} label="views" />

      {delta === null ? null : (
        <span
          title={`${metric(was)} views over the ${days} days before this window.`}
          className="inline-flex items-center gap-1 rounded-full bg-foreground/[0.06] px-2 py-0.5 text-xs font-medium text-foreground tabular-nums"
        >
          {up ? "▲" : "▼"}
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
      <strong className="font-semibold tracking-tight text-foreground tabular-nums">
        {value}
      </strong>{" "}
      {label}
    </span>
  );
}

const ROW_PADDING = "gap-5 px-5 py-3";
const NUMBER_RIGHT = "w-16 shrink-0 text-right";

/** A row that opens in place. `grid-template-rows: 0fr → 1fr` so the panel
 *  reverses from where it actually is mid-animation, and `inert` while closed
 *  keeps its controls out of the tab order and the a11y tree. */
function VideoRow({
  video,
  rank,
  share,
  open,
  onToggle,
}: {
  video: YoutubeVideo;
  rank: number;
  share: number;
  open: boolean;
  onToggle: () => void;
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
          "transition-colors duration-100 hover:bg-muted/40 active:bg-muted/70",
          "focus-visible:ring-ring/50 focus-visible:ring-2 focus-visible:ring-inset",
        )}
      >
        <span
          className={cn(
            "w-6 shrink-0 text-right font-mono text-xs tabular-nums",
            rank <= 3 ? "font-semibold text-gold" : "text-muted-foreground",
          )}
        >
          {rank}
        </span>

        {/* The thumbnail — real at this size, unlike a Facebook composite. */}
        <Thumbnail src={video.thumbnail_url} className="hidden w-24 shrink-0 lg:block" />

        {/* Title + kind chip. The title IS the row's text; kind is an
            attribute beside it, so the chip is MetaChip-neutral. */}
        <span className="flex min-w-0 flex-1 items-center gap-2">
          <span className="min-w-0 flex-1 truncate text-sm font-medium">
            {video.title}
          </span>
          {video.kind ? (
            <span className="inline-flex shrink-0 items-center gap-1 rounded-[5px] bg-muted px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground">
              {video.kind === "short" ? (
                <RectangleHorizontal className="size-3" />
              ) : (
                <Film className="size-3" />
              )}
              {video.kind === "short" ? "Short" : "Video"}
            </span>
          ) : null}
        </span>

        {/* Watch seconds — the retention signal. Seconds are honest at any
            magnitude (a short's 30s IS a full watch), so no bar, just the
            figure. */}
        <span className={cn(NUMBER_RIGHT, "w-16 hidden sm:block lg:block")}>
          <span className="font-mono text-[11px] text-muted-foreground tabular-nums">
            {video.avg_watch_s != null ? `${Math.round(video.avg_watch_s)}s` : "—"}
          </span>
        </span>

        {/* Views with a bar against the window's best — the "fall-off at a
            glance" the Facebook overview uses for engagement, applied to the
            number the list is actually sorted by. */}
        <span className="flex w-32 shrink-0 items-center justify-end gap-3">
          <span
            aria-hidden
            className="hidden h-1.5 w-16 rounded-full bg-foreground/10 sm:block"
          >
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
            {metric(video.views)}
          </span>
        </span>

        <span className="hidden w-24 shrink-0 text-right font-mono text-[11px] text-muted-foreground sm:block">
          {timeAgo(video.published_at)}
        </span>

        <ChevronRight
          aria-hidden
          className={cn(
            "size-4 shrink-0 text-muted-foreground",
            "transition-transform duration-200 ease-[cubic-bezier(0.32,0.72,0,1)] motion-reduce:transition-none",
            open && "rotate-90",
          )}
        />
      </button>

      <div
        className={cn(
          "grid transition-[grid-template-rows] ease-[cubic-bezier(0.32,0.72,0,1)] motion-reduce:transition-none",
          open ? "grid-rows-[1fr] duration-300" : "grid-rows-[0fr] duration-200",
        )}
      >
        <div className="overflow-hidden" inert={!open}>
          <div
            className={cn(
              "transition-[opacity,translate] duration-200 ease-out",
              "motion-reduce:translate-y-0 motion-reduce:transition-[opacity]",
              open ? "translate-y-0 opacity-100 delay-75" : "-translate-y-1 opacity-0",
            )}
          >
            <VideoDetail video={video} />
          </div>
        </div>
      </div>
    </div>
  );
}

/** The panel under an opened row: a larger thumbnail, the breakdown, the action. */
function VideoDetail({ video }: { video: YoutubeVideo }) {
  return (
    <div className="flex flex-col gap-5 px-5 pt-2 pb-7 sm:flex-row sm:gap-6 sm:pt-3 sm:pr-8 sm:pb-8 sm:pl-16">
      <Thumbnail src={video.thumbnail_url} className="w-48 sm:w-64" />

      <div className="min-w-0 flex-1 space-y-4">
        <div>
          <h3 className="text-sm font-semibold leading-snug">{video.title}</h3>
          <p className="mt-1 text-[11px] text-muted-foreground">
            {video.kind ? `${video.kind === "short" ? "Short" : "Video"}` : null}
            {video.kind && video.published_at ? " · " : ""}
            {video.published_at ? (
              <span title={fullDate(video.published_at)}>
                Published {timeAgo(video.published_at)}
              </span>
            ) : null}
          </p>
        </div>

        {/* The breakdown as a stat grid — the number carries the weight, the
            word beneath it does not, the same Figure rule as the summary. */}
        <dl className="flex flex-wrap gap-x-8 gap-y-3">
          <Stat value={metric(video.views)} label="Views" />
          <Stat value={metric(video.likes)} label="Likes" />
          <Stat value={metric(video.comments)} label="Comments" />
          <Stat value={metric(video.shares)} label="Shares" />
          {video.avg_watch_s != null ? (
            <Stat value={`${Math.round(video.avg_watch_s)}s`} label="Avg watch" />
          ) : null}
        </dl>

        {video.watch_url ? (
          <Button variant="outline" size="sm" asChild>
            <a href={video.watch_url} target="_blank" rel="noreferrer">
              <ExternalLink className="size-3.5" />
              Watch on YouTube
            </a>
          </Button>
        ) : null}
      </div>
    </div>
  );
}

/** One stat of the detail grid: the number carries the weight, the word does not. */
function Stat({ value, label }: { value: string; label: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <dd className="text-sm font-semibold tracking-tight text-foreground tabular-nums">
        {value}
      </dd>
      <dt className="font-mono text-[10px] tracking-[0.12em] text-muted-foreground uppercase">
        {label}
      </dt>
    </div>
  );
}

/** The video's frame, or a stand-in. 16:9 — YouTube frames are widescreen,
 *  unlike the Facebook composites' 4:5. */
function Thumbnail({ src, className }: { src: string | null; className?: string }) {
  if (!src) {
    return (
      <div
        className={cn(
          "flex aspect-16/9 shrink-0 items-center justify-center rounded-lg border bg-muted",
          className,
        )}
      >
        <Play className="size-4 text-muted-foreground/50" />
      </div>
    );
  }
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={src}
      alt=""
      loading="lazy"
      className={cn(
        "aspect-16/9 shrink-0 rounded-lg border bg-muted object-cover",
        className,
      )}
    />
  );
}