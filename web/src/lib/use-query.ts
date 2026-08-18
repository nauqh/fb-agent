"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { subscribe } from "@/lib/store";

interface QueryOptions<T> {
  /**
   * Re-run on a timer as well.
   *
   * Server state is polled, not streamed — a run is measured in tens of
   * seconds and polling is what the old system did. Screens watching a row in
   * flight set this; everything else relies on the store notification, which
   * stands in for the operator refreshing.
   */
  intervalMs?: number;
  /**
   * Keep polling only while this holds.
   *
   * A Draft that has left `generating` will never change again on its own, so
   * polling it is pure noise — and noise that never lets the page go idle.
   */
  pollWhile?: (data: T | null) => boolean;
  /** Skip the query entirely (e.g. no id resolved yet). */
  enabled?: boolean;
}

interface QueryResult<T> {
  data: T | null;
  error: string | null;
  /**
   * No answer yet — **including while the query is disabled**.
   *
   * It used to start as `enabled`, so a query waiting on its Page id reported
   * `loading: false` with `data: null`, and every screen testing
   * `loading && !data` fell straight through to its "draw the list" branch: the
   * Review queue painted a table header over no rows, Sources painted an empty
   * grid. Locally that beat is ~100ms and it went unseen for months; it was
   * found by holding every API response for nine seconds to photograph the
   * loading states.
   *
   * Now it means what a caller assumes it means, so `loading` alone is a
   * sufficient test. It goes false only once an attempt has *finished* —
   * settled with rows or settled with an error — which is also why a refetch
   * does not flip it back on and flash the screen it already drew.
   *
   * A query disabled forever would therefore read as loading forever. Every
   * `enabled` in this codebase is a `pageId !== null` that resolves in one
   * fetch; a genuinely permanent one would need its own answer.
   */
  loading: boolean;
  refresh: () => Promise<void>;
}

export function useQuery<T>(
  loader: () => Promise<T>,
  deps: unknown[],
  options: QueryOptions<T> = {},
): QueryResult<T> {
  const { intervalMs, pollWhile, enabled = true } = options;

  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Whether an attempt has finished, rather than whether one is in flight. See
  // `loading` on `QueryResult` for what that distinction cost.
  const [settled, setSettled] = useState(false);

  /**
   * The loader closes over props and so is a new function every render.
   * Re-running the effect on it would refetch on every render, so it is held in
   * a ref that is updated *in an effect* — assigning during render is what the
   * refs rule forbids, and it is forbidden for a real reason: a render that
   * React throws away would still have mutated it.
   */
  const loaderRef = useRef(loader);
  useEffect(() => {
    loaderRef.current = loader;
  });

  const run = useCallback(async () => {
    try {
      setData(await loaderRef.current());
      setError(null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setSettled(true);
    }
  }, []);

  /**
   * Reset to loading when the query identity changes — adjusting state during
   * render rather than in an effect, so there is no flash of the previous
   * Draft's data while the next one is in flight.
   */
  const key = JSON.stringify(deps);
  const [renderedKey, setRenderedKey] = useState(key);
  if (key !== renderedKey) {
    setRenderedKey(key);
    setData(null);
    setError(null);
    setSettled(false);
  }

  useEffect(() => {
    if (!enabled) return;
    void run();
    // The store notification stands in for a refetch: any api call that mutates
    // a table emits, and every open query re-reads.
    return subscribe(() => void run());
  }, [enabled, run, key]);

  const polling = Boolean(intervalMs) && (pollWhile ? pollWhile(data) : true);
  useEffect(() => {
    if (!enabled || !intervalMs || !polling) return;
    const timer = setInterval(() => void run(), intervalMs);
    return () => clearInterval(timer);
  }, [enabled, intervalMs, polling, run]);

  return { data, error, loading: !settled, refresh: run };
}
