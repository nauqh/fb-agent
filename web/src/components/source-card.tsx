"use client";

import { useState } from "react";
import { Check, ImageOff, Loader2, MessageCircle, Repeat2, ThumbsUp } from "lucide-react";

import type { SourceKind } from "@/lib/types";
import { isFactual } from "@/lib/types";
import { metric, timeAgo } from "@/lib/format";
import { cn } from "@/lib/utils";

/**
 * One browsable Source Item.
 *
 * The card states which way the subject binds, because that is the single most
 * consequential thing about a Source Item and it is invisible otherwise: a
 * competitor post (`competitor_post`) is borrowed for *tone*, an RSS item or tweet
 * binds the *story*.
 * Getting it backwards produces confident, well-formed output about the wrong
 * subject, and nothing downstream catches it.
 */
export function SourceCard({
  kind,
  author,
  text,
  url,
  image_url,
  published_at,
  reactions,
  comments,
  shares,
  selected,
  pending,
  onToggle,
}: {
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
}) {
  const factual = isFactual(kind);

  return (
    <button
      type="button"
      onClick={onToggle}
      disabled={pending}
      className={cn(
        "group relative flex h-full flex-col gap-3 rounded-lg border p-4 text-left transition-colors",
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

        <span
          className={cn(
            "flex size-5 shrink-0 items-center justify-center rounded border transition-colors",
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
 * tick time, alongside the Phase 4 download-and-store.
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
function SourceThumbnail({ src }: { src?: string | null }) {
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
      <div className="flex size-16 shrink-0 items-center justify-center rounded-md bg-muted">
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
      className="size-16 shrink-0 rounded-md object-cover"
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
