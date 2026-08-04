"use client";

import { useCallback, useSyncExternalStore } from "react";
import type { DraftStatus } from "@/lib/types";

/**
 * Which statuses the Review queue is showing.
 *
 * Module state rather than a search param, because the queue has to keep its
 * filter while the operator navigates between `/review/[id]` children, and a
 * param would have to be threaded through every list link to survive. Defaults
 * to `review` so the queue drains as drafts are decided.
 */
type Filter = DraftStatus | "all";

let current: Filter = "review";
const listeners = new Set<() => void>();

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useReviewFilter() {
  const status = useSyncExternalStore(
    subscribe,
    () => current,
    () => "review" as Filter,
  );

  const setStatus = useCallback((next: Filter) => {
    current = next;
    for (const listener of listeners) listener();
  }, []);

  return { status, setStatus };
}

/** For code outside React that needs to know what the queue is showing. */
export function currentReviewFilter(): Filter {
  return current;
}
