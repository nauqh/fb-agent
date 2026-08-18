import { Loader2 } from "lucide-react";

import { cn } from "@/lib/utils";

/**
 * Waiting for data: a spinner, centred in the space the content will fill.
 *
 * This replaced the grey `Skeleton` blocks across every screen on 2026-08-18.
 * The skeletons were meant to trace the shape of what was coming, and after a
 * year of edits they no longer did — five `h-20` bars stood in for a table with
 * a header and a pager, one `h-40` stood in for a rail *and* a pane. A wrong
 * silhouette is worse than no silhouette: it settles into a different layout
 * the moment the data lands, and while it is up it reads as content that failed
 * to render rather than as a wait.
 *
 * A spinner says the one true thing — something is in flight — and says it the
 * same way everywhere, which is what makes it read as the app rather than as
 * six screens each guessing.
 *
 * `Skeleton` itself stays for the one job it is still right for: a placeholder
 * that really is the shape of the thing, like the 8px allowance meter on
 * Global, where a spinner does not fit and a grey bar is exactly the bar.
 */
export function Loading({
  label,
  className,
}: {
  /** What is being fetched. Omit for small inline waits. */
  label?: string;
  /** Height of the reserved space — `h-40`, `aspect-square`, and so on. */
  className?: string;
}) {
  return (
    <div
      role="status"
      aria-live="polite"
      className={cn(
        "flex min-h-24 w-full flex-col items-center justify-center gap-3",
        className,
      )}
    >
      <Loader2 className="size-5 animate-spin text-muted-foreground" />
      {label ? (
        // Mono uppercase, like every other piece of metadata in the app. It is
        // a status, not prose.
        <p className="font-mono text-[11px] tracking-[0.12em] text-muted-foreground uppercase">
          {label}
        </p>
      ) : null}
    </div>
  );
}
