"use client";

import { Check, Loader2, MessageCircle, Repeat2, ThumbsUp } from "lucide-react";

import type { SourceKind } from "@/lib/types";
import { isFactual } from "@/lib/types";
import { metric, timeAgo } from "@/lib/format";
import { cn } from "@/lib/utils";

/**
 * One browsable Source Item.
 *
 * The card states which way the subject binds, because that is the single most
 * consequential thing about a Source Item and it is invisible otherwise: a
 * rival post is borrowed for *tone*, an article or tweet binds the *story*.
 * Getting it backwards produces confident, well-formed output about the wrong
 * subject, and nothing downstream catches it.
 */
export function SourceCard({
  kind,
  author,
  text,
  url,
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

      <p className="line-clamp-5 flex-1 text-sm leading-relaxed text-foreground/85">{text}</p>

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

function hostname(url: string | null): string {
  if (!url) return "";
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}
