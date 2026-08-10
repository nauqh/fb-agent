import type React from "react";

import { cn } from "@/lib/utils";

/**
 * One titled block on a configuration screen.
 *
 * Shared by Settings and Global rather than copied, because the two screens are
 * a pair: Settings answers "this Page", Global answers "the account", and a
 * card that looked different on one of them would imply a difference in kind
 * that is not there.
 *
 * Was a `<div>` plus a `<Separator>` repeated down a single column; as cards in
 * a grid the screen uses the width the shell gives it, and a section can move
 * without dragging a separator with it.
 */
export function Card({
  title,
  hint,
  meta,
  className,
  children,
}: {
  title: string;
  hint?: React.ReactNode;
  meta?: React.ReactNode;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <section className={cn("rounded-xl border bg-card p-5", className)}>
      <div className="flex items-start justify-between gap-4 pb-4">
        <div className="min-w-0">
          {/* Full-strength text, never muted. A card's title is the one thing on
              it that has to read first; grey it and the block looks disabled. */}
          <h2 className="text-[15px] font-semibold tracking-tight">{title}</h2>
          {hint ? <p className="pt-1 text-xs text-muted-foreground">{hint}</p> : null}
        </div>
        {meta}
      </div>
      {children}
    </section>
  );
}

/** A count in a card's top-right. `tabular-nums` so digits do not jitter. */
export function Counts({ children }: { children: React.ReactNode }) {
  return (
    <span className="shrink-0 whitespace-nowrap text-xs tabular-nums text-muted-foreground">
      {children}
    </span>
  );
}
