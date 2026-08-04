"use client";

import { useState } from "react";
import {
  Check,
  ExternalLink,
  Eye,
  ImageOff,
  Loader2,
  MessageCircle,
  Repeat2,
  ThumbsUp,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type { SourceKind } from "@/lib/types";
import { isFactual } from "@/lib/types";
import { chars, fullDate, metric, timeAgo } from "@/lib/format";
import { cn } from "@/lib/utils";

/** What each kind is called on screen. The stored values are not operator-facing. */
const KIND_LABEL: Record<SourceKind, string> = {
  competitor_post: "Competitor post",
  tweet: "Tweet",
  rss: "RSS item",
};

interface SourceCardProps {
  kind: SourceKind;
  author: string | null;
  text: string;
  url: string | null;
  image_url?: string | null;
  /** Snake case so a `SourceItem` can be spread straight onto this card. */
  published_at: string | null;
  reactions?: number | null;
  comments?: number | null;
  shares?: number | null;
  selected: boolean;
  pending?: boolean;
  onToggle: () => void;
}

/**
 * One browsable Source Item.
 *
 * The card states which way the subject binds, because that is the single most
 * consequential thing about a Source Item and it is invisible otherwise: a
 * competitor post (`competitor_post`) is borrowed for *tone*, an RSS item or tweet
 * binds the *story*.
 * Getting it backwards produces confident, well-formed output about the wrong
 * subject, and nothing downstream catches it.
 *
 * Clicking the card ticks it, as it always has — the grid is a bulk picker and
 * ticking is the frequent action, so it keeps the whole surface. Reading the
 * full post is the rare one and gets the small corner button. The expand button
 * is a *sibling* of the card button rather than a child: nesting one `<button>`
 * inside another is invalid HTML and browsers recover from it by dropping the
 * inner one.
 */
export function SourceCard({ selected, pending, onToggle, ...item }: SourceCardProps) {
  const [open, setOpen] = useState(false);
  const { author, text, url, image_url, published_at, reactions, comments, shares } = item;
  const factual = isFactual(item.kind);

  return (
    <div className="relative h-full">
      <button
        type="button"
        onClick={onToggle}
        disabled={pending}
        className={cn(
          "group flex h-full w-full flex-col gap-3 rounded-lg border p-4 text-left transition-colors",
          "hover:border-foreground/25 disabled:opacity-60",
          selected && "border-gold bg-gold/[0.06] hover:border-gold",
        )}
      >
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 space-y-1">
            <p className="truncate text-sm font-medium">{author ?? "Unknown"}</p>
            <p className="text-xs text-muted-foreground">
              <span className={cn(factual ? "text-foreground/70" : "")}>
                {factual ? "Binds the story" : "Style only"}
              </span>
              <span className="mx-1.5">·</span>
              {timeAgo(published_at)}
            </p>
          </div>

          {/* Wide enough for the tick box *and* the expand button sitting over
              the gap beside it. Reserving the width here rather than nudging
              the button is what keeps a long author name from running
              underneath a control that is not part of this flex row. */}
          <span className="flex w-14 shrink-0 justify-end">
            <span
              className={cn(
                "flex size-5 items-center justify-center rounded border transition-colors",
                selected
                  ? "border-gold bg-gold text-gold-foreground"
                  : "border-input group-hover:border-foreground/40",
              )}
            >
              {pending ? (
                <Loader2 className="size-3 animate-spin" />
              ) : selected ? (
                <Check className="size-3.5" strokeWidth={3} />
              ) : null}
            </span>
          </span>
        </div>

        <div className="flex flex-1 gap-3">
          <SourceThumbnail src={image_url} />
          <p className="line-clamp-5 flex-1 text-sm leading-relaxed text-foreground/85">{text}</p>
        </div>

        <div className="flex items-center justify-between gap-3 text-xs text-muted-foreground">
          {reactions !== null && reactions !== undefined ? (
            <span className="flex items-center gap-3 tabular-nums">
              <span className="flex items-center gap-1">
                <ThumbsUp className="size-3" /> {metric(reactions)}
              </span>
              <span className="flex items-center gap-1">
                <MessageCircle className="size-3" /> {metric(comments ?? null)}
              </span>
              <span className="flex items-center gap-1">
                <Repeat2 className="size-3" /> {metric(shares ?? null)}
              </span>
            </span>
          ) : (
            <span className="truncate">{hostname(url)}</span>
          )}
        </div>
      </button>

      {/* Beside the tick box, on the same optical line, so the card's two
          controls read as one cluster instead of one floating over the metrics.
          `right-10` is the tick box (16px inset, 20px wide) plus a 4px gap.
          Always visible, not hover-only: a control that appears on hover does
          not exist on a touch screen, and this is the only way to the text the
          card clamps away. */}
      <Button
        variant="ghost"
        size="icon-xs"
        className="absolute top-3.5 right-10 text-muted-foreground hover:text-foreground"
        onClick={() => setOpen(true)}
      >
        <Eye />
        <span className="sr-only">View the full post</span>
      </Button>

      <Dialog open={open} onOpenChange={setOpen}>
        {/* One fixed size for every post, so opening a second card does not
            resize the window under the cursor — a 40-character tweet and a
            2,000-character article get the same box. The height is capped
            against the viewport for short laptop screens, and the three rows
            pin the header and footer while only the middle scrolls. */}
        <DialogContent className="grid h-[min(38rem,85vh)] grid-rows-[auto_minmax(0,1fr)_auto] sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle className="truncate pr-8">{author ?? "Unknown"}</DialogTitle>
            <DialogDescription>
              {KIND_LABEL[item.kind]}
              <span className="mx-1.5">·</span>
              {factual ? "Binds the story" : "Style only"}
              <span className="mx-1.5">·</span>
              {fullDate(published_at)}
            </DialogDescription>
          </DialogHeader>

          {/* The only scroller. `min-h-0` is load-bearing: a grid row's default
              `auto` minimum refuses to shrink below its content, and without it
              the row grows past the fixed height and the footer leaves the box
              instead of the text scrolling. */}
          <div className="min-h-0 space-y-4 overflow-y-auto">
            {/* Centred on its own backdrop rather than stretched to the dialog
                width: the source is a 130px thumbnail (see `SourceThumbnail`)
                and upscaling it four times only makes the blur bigger. */}
            {image_url ? (
              <div className="flex justify-center rounded-md bg-muted p-3">
                <SourceThumbnail src={image_url} className="size-32 rounded" />
              </div>
            ) : null}

            <p className="text-sm leading-relaxed whitespace-pre-wrap">
              {text || <span className="text-muted-foreground">No text.</span>}
            </p>

            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground tabular-nums">
              <span>{chars(text)}</span>
              {reactions !== null && reactions !== undefined ? (
                <>
                  <span>{metric(reactions)} reactions</span>
                  <span>{metric(comments ?? null)} comments</span>
                  <span>{metric(shares ?? null)} shares</span>
                </>
              ) : null}
            </div>
          </div>

          <DialogFooter>
            {url ? (
              <Button variant="outline" asChild>
                <a href={url} target="_blank" rel="noreferrer">
                  <ExternalLink />
                  Open original
                </a>
              </Button>
            ) : null}
            <Button
              variant={selected ? "outline" : "default"}
              disabled={pending}
              onClick={onToggle}
            >
              {pending ? <Loader2 className="animate-spin" /> : selected ? <Check /> : null}
              {selected ? "Remove from Cart" : "Add to Cart"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

/**
 * The post's picture, or a placeholder.
 *
 * **Deliberately small.** Metricool serves a 130×130 thumbnail and nothing
 * larger — `stp=dst-jpg_s130x130_tt6`, and the URL signature covers that
 * parameter, so asking for s480/s720/p720 or dropping `stp` all return 403. The
 * payload carries no HD field either. Rendered at 64px it is sharp on a 1x
 * display and near-native on a 2x one; the old system stretched the same 130px
 * across the full card width and was blurry for exactly this reason.
 *
 * A bigger image does exist — the post's own `og:image` is 600×750 and is
 * readable without auth — but that is one extra request against facebook.com
 * per post, which is not something to do 60 times per grid load. It belongs at
 * tick time, alongside the Phase 4 download-and-store, or behind the detail
 * dialog above, which opens one post at a time.
 *
 * `onError` is not decoration. Facebook's CDN URLs are signed and expire about
 * four days after they are issued, and Metricool hands back a freshly signed one
 * on every sync — so what is on screen is normally fine, but anything not just
 * synced is a 403. The old system rendered these with no error handling and its
 * stored URLs are, right now, all dead: four sampled production rows expired on
 * 2026-07-31 and return 403 today.
 *
 * A plain `<img>`, not `next/image`: the optimizer would need every fbcdn host
 * in `remotePatterns`, and it would cache a URL built to expire.
 */
function SourceThumbnail({ src, className }: { src?: string | null; className?: string }) {
  const [failed, setFailed] = useState(false);

  // A refreshed sync can replace a dead URL with a live one, so the failure has
  // to clear when `src` changes. Adjusted during render rather than in an
  // effect — the same pattern as `use-query.ts` — because an effect would show
  // the placeholder for one frame before correcting itself.
  const [renderedSrc, setRenderedSrc] = useState(src);
  if (src !== renderedSrc) {
    setRenderedSrc(src);
    setFailed(false);
  }

  if (!src || failed) {
    return (
      <div
        className={cn(
          "flex size-16 shrink-0 items-center justify-center rounded-md bg-muted",
          className,
        )}
      >
        <ImageOff className="size-4 text-muted-foreground/50" aria-hidden />
        <span className="sr-only">No image</span>
      </div>
    );
  }

  return (
    // eslint-disable-next-line @next/next/no-img-element -- deliberate, see above
    <img
      src={src}
      alt=""
      loading="lazy"
      className={cn("size-16 shrink-0 rounded-md object-cover", className)}
      onError={() => setFailed(true)}
    />
  );
}

function hostname(url: string | null): string {
  if (!url) return "";
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}
