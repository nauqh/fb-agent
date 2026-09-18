"use client";

import { useSyncExternalStore } from "react";

import { hasPendingRequests, subscribeProgress } from "@/lib/store";

/**
 * A quiet global signal for work that is not tied to one visible panel.
 *
 * The page-level loaders explain the first load. This line covers refetches,
 * route changes and writes while leaving the current screen in place. The
 * 100ms transition delay keeps fast requests from flashing at the top of the
 * window.
 */
export function RequestProgress() {
  const pending = useSyncExternalStore(
    subscribeProgress,
    hasPendingRequests,
    () => false,
  );

  return (
    <div
      aria-hidden={!pending}
      aria-label={pending ? "Loading" : undefined}
      data-pending={pending}
      role="status"
      className="pointer-events-none fixed inset-x-0 top-0 z-[100] h-0.5 opacity-0 transition-opacity delay-100 duration-150 data-[pending=true]:opacity-100"
    >
      <div className="absolute inset-y-0 w-1/3 animate-progress-sweep bg-gold" />
    </div>
  );
}
