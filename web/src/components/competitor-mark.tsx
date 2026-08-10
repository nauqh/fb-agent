"use client";

import { useState } from "react";

import { cn } from "@/lib/utils";

/**
 * A competitor's logo, wherever one is listed.
 *
 * Shared so that every list of competitors shows the same thing. A row of names
 * alone is unreadable at twenty-plus entries — the logo is how an operator finds
 * the one they mean, and several of these pages have near-identical names
 * ("Historical facts", "History Addicts", "History Remembered").
 *
 * The picture is Facebook's CDN, signed and expiring in about four days. Safe to
 * render only because the competitor list is never stored — the server re-reads
 * it live on every request, so the URL reaching the browser is minutes old.
 * `onError` still matters: an expired or blocked URL must degrade to the initial
 * rather than to a broken-image icon, which is what a stale one looks like.
 */
export function CompetitorMark({
  name,
  picture,
  className,
}: {
  name: string;
  picture?: string | null;
  className?: string;
}) {
  const [broken, setBroken] = useState(false);

  if (picture && !broken) {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={picture}
        alt=""
        onError={() => setBroken(true)}
        className={cn("size-8 shrink-0 rounded-full border object-cover", className)}
      />
    );
  }

  return (
    <span
      className={cn(
        "flex size-8 shrink-0 items-center justify-center rounded-full bg-muted text-[11px] font-semibold text-muted-foreground",
        className,
      )}
    >
      {name.slice(0, 1).toUpperCase()}
    </span>
  );
}
