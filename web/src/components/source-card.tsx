"use client";

import { useState } from "react";
import {
  Bird,
  Check,
  ExternalLink,
  Eye,
  ImageOff,
  Loader2,
  MessageCircle,
  Newspaper,
  Repeat2,
  ThumbsUp,
  Users,
  XIcon,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { CompetitorMark } from "@/components/competitor-mark";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Dialog as DialogPrimitive } from "radix-ui";
import { MetaChip } from "@/components/meta-chip";
import type { SourceKind } from "@/lib/types";
import { competitorAvatar } from "@/lib/competitor-avatar";
import { chars, fullDate, metric, timeAgo } from "@/lib/format";
import { cn } from "@/lib/utils";

/** What each kind is called on screen. The stored values are not operator-facing.
 *
 *  Exported because the review drawer names the source a Draft came from and has
 *  to call it the same thing the grid did — the operator is being asked to
 *  recognise a card they ticked. */
export const KIND_LABEL: Record<SourceKind, string> = {
  competitor_post: "Competitor post",
  tweet: "Tweet",
  rss: "RSS item",
};

/** Stands in for a picture there never was. See `SourceThumbnail`. */
export const KIND_GLYPH: Record<SourceKind, typeof Users> = {
  competitor_post: Users,
  tweet: Bird,
  rss: Newspaper,
};

interface SourceCardProps {
  kind: SourceKind;
  author: string | null;
  /**
   * The competitor's Facebook page id, for their logo. competitor_post only.
   *
   * Optional because the other two kinds have no logo to show and the Cart
   * spreads a stored item straight onto this card.
   */
  competitor_page_id?: string | null;
  text: string;
  url: string | null;
  image_url?: string | null;
  /** Snake case so a `SourceItem` can be spread straight onto this card. */
  published_at: string | null;
  reactions?: number | null;
  comments?: number | null;
  shares?: number | null;
  /** A Draft already came from this one. Competitor posts only. */
  used?: boolean;
  selected: boolean;
  pending?: boolean;
  onToggle: () => void;
}

/**
 * One browsable Source Item.
 *
 * How a kind binds the writer is not stated here, and as of 2026-08-18 there is
 * nothing left to state: every kind binds its story, competitor posts included.
 * The card used to say otherwise in two words that raised more questions than
 * they answered.
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
  const { author, text, url, image_url, published_at, reactions, comments, shares, used } = item;
  const logo = competitorAvatar(item.competitor_page_id ?? null);

  return (
    <div className="relative h-full">
      <button
        type="button"
        onClick={onToggle}
        disabled={pending}
        className={cn(
          "group flex h-full w-full flex-col gap-3 rounded-2xl border p-4 text-left transition-colors",
          "hover:border-foreground/25 disabled:opacity-60",
          selected && "border-gold bg-gold/[0.06] hover:border-gold",
          // Dimmed, not hidden or disabled. A post worth writing twice exists —
          // a different angle on the same story — so this is a warning, not a
          // rule. Hiding it would also make the grid shrink for reasons the
          // operator cannot see.
          used && !selected && "opacity-55",
        )}
      >
        <div className="flex items-start justify-between gap-3">
          {/* The logo, where there is one. A grid of 60 competitor posts is
              read by author before it is read by text, and several of these
              pages have near-identical names — the mark is how the operator
              tells them apart at a glance. Tweets and RSS items have none and
              take the width instead. */}
          {logo ? (
            <CompetitorMark
              name={author ?? "?"}
              picture={logo}
              className="size-9 mt-0.5"
            />
          ) : null}
          <div className="min-w-0 flex-1 space-y-1">
            <p className="flex items-center gap-1.5 truncate text-sm font-medium">
              {author ?? "Unknown"}
              {used ? (
                <MetaChip className="ml-0.5">used</MetaChip>
              ) : null}
            </p>
            <p className="flex items-center gap-1.5">
              <MetaChip>{KIND_LABEL[item.kind]}</MetaChip>
              <span className="truncate text-xs text-muted-foreground">
                {timeAgo(published_at)}
              </span>
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
            <MetaChip className="min-w-0 shrink">
              <span className="truncate">{hostname(url)}</span>
            </MetaChip>
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
      {/* Fit the copy. The dialog grows to the post's length (capped at 85vh so
          a genuinely long one scrolls), and the image sits as a single corner
          cell — Word's “squared” wrapping — rather than taking its own column.
          That is the whole rework: one cell, image top-right beside the title,
          story beneath it in the same column. */}
      <DialogContent
        showCloseButton={false}
        className="flex max-h-[85vh] flex-col overflow-hidden rounded-2xl p-0 sm:max-w-[46rem]"
      >
        {/* One story column that flexes to the copy. `flex-1` is what pins the
            actions: the story takes the leftover height and scrolls inside it,
            so a long post never pushes the dock off the foot of the box. */}
        <div className="relative min-w-0 min-h-0 flex-1 overflow-y-auto p-5">
          <DialogPrimitive.Close data-slot="dialog-close" asChild>
            <Button variant="ghost" size="icon-sm" className="absolute top-2 right-2">
              <XIcon />
              <span className="sr-only">Close</span>
            </Button>
          </DialogPrimitive.Close>

          <div className="space-y-3">
            {/* The image floated right, squared: it takes its own rectangle and
                the story flows around it instead of bending to its full height.
                It must be a normal-flow sibling — not inside flex, where a float
                would become its own full row and produce the white band under
                the title. `clear-both` on the stats bar ends the wrap so the
                rule spans full width. */}
            {image_url ? (
              <SourceThumbnail
                src={image_url}
                className="float-left mr-3 my-1 w-28 rounded-xl"
              />
            ) : null}

            <div className="flex flex-wrap items-center gap-2">
              <MetaChip>{KIND_LABEL[item.kind]}</MetaChip>
              <span className="text-xs text-muted-foreground">
                {fullDate(published_at)}
                <span aria-hidden> · </span>
                {timeAgo(published_at)}
              </span>
            </div>
            <DialogTitle className="truncate">{author ?? "Unknown"}</DialogTitle>

            <p className="text-sm leading-relaxed whitespace-pre-wrap">
              {text || <span className="text-muted-foreground">No text.</span>}
            </p>

            <div className="clear-both flex flex-wrap items-center gap-x-4 gap-y-1 border-t pt-3 font-mono text-[11px] text-muted-foreground tabular-nums">
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
        </div>

        {/* Actions dock at the foot, full width — the post's own row. */}
        <div className="flex flex-wrap items-center justify-end gap-2 border-t bg-muted/40 px-4 py-3">
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
        </div>
      </DialogContent>
      </Dialog>
    </div>
  );
}

/**
 * The post's picture, or a broken-image mark when one was expected and failed.
 * Nothing is drawn when the post never had an image — the text row takes the width.
 *
 * **Small, but no longer tiny.** Metricool serves a 130×130 thumbnail and
 * nothing larger — `stp=dst-jpg_s130x130_tt6`, and the URL signature covers that
 * parameter, so asking for s480/s720/p720 or dropping `stp` all return 403. The
 * payload carries no HD field either. The old system stretched that 130px across
 * the full card width and was blurry for exactly this reason.
 *
 * 88px is the deliberate middle. It is native on a 1x display and 1.35x
 * upscaled on a 2x one, which is soft under close inspection and invisible at
 * arm's length; 64px was sharp everywhere and read as an afterthought beside the
 * text. Past ~104px the upscale starts to smear, so this is not a knob to keep
 * turning. RSS and tweet images are full size and cropped square, so they only
 * get sharper.
 *
 * A picture that loaded and *failed* still gets `ImageOff`, because that one is
 * damage — as opposed to a post that never had a picture, which shows nothing.
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
function SourceThumbnail({
  src,
  className,
}: {
  src?: string | null;
  className?: string;
}) {
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

  // No picture at all — nothing to show, so no tile. A placeholder here made
  // a post that never had an image look like one whose image had broken, and at
  // four imageless items per screen that is a row of silent damage. Omitting
  // the tile entirely lets the text take the width instead.
  const tile = "size-22 shrink-0 rounded-2xl inset-ring inset-ring-foreground/10";

  if (!src) return null;

  if (failed) {
    // A picture that loaded and failed is a broken tile, not an absent one —
    // `ImageOff` marks real damage rather than a post that simply had no image.
    return (
      <div className={cn(tile, "flex items-center justify-center bg-muted", className)}>
        <ImageOff className="size-5.5 text-muted-foreground/45" aria-hidden />
        <span className="sr-only">Image unavailable</span>
      </div>
    );
  }

  return (
    // eslint-disable-next-line @next/next/no-img-element -- deliberate, see above
    <img
      src={src}
      alt=""
      loading="lazy"
      className={cn(tile, "bg-muted object-cover", className)}
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
