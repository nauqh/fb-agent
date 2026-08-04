"use client";

import { AlertCircle, RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/button";

/**
 * What a failed read looks like.
 *
 * `useQuery` catches, leaves `data` null and sets `error` — so a screen that
 * destructures only `{ data }` renders an empty list and says nothing. That is
 * the worst possible outcome here, because empty is *also* what a quiet week
 * looks like, and the two are indistinguishable on screen.
 *
 * It is not hypothetical. Metricool returned a 502 on 2026-08-04 and the
 * Competitors tab showed an empty grid with no explanation. The API had already
 * done its part — `GET /sources/competitors` answers 502 with a sentence
 * written for the operator ("Metricool /posts did not answer: ReadTimeout")
 * precisely so this cannot be misread. The client was dropping it.
 *
 * So the message is shown verbatim. `lib/api/client.ts` surfaces FastAPI's
 * `detail` unchanged for the same reason: it is the only part that says what to
 * do next.
 */
export function QueryError({
  error,
  onRetry,
  className,
}: {
  error: string;
  onRetry?: () => void;
  className?: string;
}) {
  return (
    <div
      role="alert"
      className={`flex items-start gap-3 rounded-lg border border-destructive/40 bg-destructive/[0.06] p-4 ${className ?? ""}`}
    >
      <AlertCircle className="mt-0.5 size-4 shrink-0 text-destructive" />
      <div className="min-w-0 flex-1 space-y-1">
        <p className="text-sm font-medium">Could not load</p>
        <p className="text-xs leading-relaxed text-muted-foreground">{error}</p>
      </div>
      {onRetry ? (
        <Button variant="outline" size="sm" onClick={onRetry} className="shrink-0">
          <RefreshCw className="size-3.5" />
          Retry
        </Button>
      ) : null}
    </div>
  );
}
