"use client";

import { cn } from "@/lib/utils";

/**
 * A tertiary attribute rendered as a quiet filled chip — polylane.com's
 * `surface-2` grammar (`bg-surface-2 px-2.5 py-1.5 text-[11px]`), shrunk to
 * this app's density and built on the existing `muted` surface token rather
 * than a bespoke `surface-2`.
 *
 * It is for the *attributes* of a row — the kind of source it is, its host,
 * a "used" flag, a count — things that identify or classify but are not the
 * row's verdict. Verdicts stay `StatusPill`, which carries a saturated dot; a
 * chip and a pill must not blur into each other, because one says "what is
 * this" and the other "what happened to it". That is why this is neutral by
 * default and only spent a colour as a quiet fill (`tone="warning"` etc.), the
 * way polylane tints a severity chip — never the pill's full-strength dot.
 */

export type MetaTone = "neutral" | "warning";

const TONE: Record<MetaTone, string> = {
  neutral: "bg-muted text-muted-foreground",
  warning: "bg-amber-500/10 text-amber-700 dark:text-amber-400",
};

export function MetaChip({
  tone = "neutral",
  className,
  children,
}: {
  tone?: MetaTone;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-[5px] px-1.5 py-0.5",
        "text-[10px] font-medium leading-tight",
        TONE[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}
