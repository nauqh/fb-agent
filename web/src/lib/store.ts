import type { Draft, SourceItem } from "@/lib/types";
import { DRAFTS } from "@/lib/fixtures/drafts";
import { PAGES } from "@/lib/fixtures/pages";
import { COMPETITOR_POSTS, SAVED_SOURCES } from "@/lib/fixtures/sources";

/**
 * The prototype's stand-in for fb_agent.db.
 *
 * A module singleton holding the three tables, mutated only by `lib/api/*`.
 * Components never import this — they call the api functions, exactly as they
 * will call `fetch` once the FastAPI routes exist. Keeping the mutation here
 * rather than in React state is what lets a background "run" advance a Draft's
 * progress columns while the operator is on another screen, which is how the
 * real thing behaves.
 */

interface Tables {
  pages: typeof PAGES;
  sourceItems: SourceItem[];
  drafts: Draft[];
  nextSourceItemId: number;
  nextDraftId: number;
}

function seed(): Tables {
  const sourceItems = [...COMPETITOR_POSTS, ...SAVED_SOURCES];
  const drafts = DRAFTS.map((draft) => ({ ...draft }));
  return {
    pages: PAGES,
    sourceItems,
    drafts,
    nextSourceItemId: Math.max(...sourceItems.map((item) => item.id)) + 1,
    nextDraftId: Math.max(...drafts.map((draft) => draft.id)) + 1,
  };
}

/**
 * Survives Fast Refresh.
 *
 * Without this every edit resets the tables and any run in flight, which makes
 * the progress UI impossible to work on.
 */
const globalForStore = globalThis as unknown as { __fbAgentStore?: Tables };
export const db: Tables = (globalForStore.__fbAgentStore ??= seed());

type Listener = () => void;
const listeners = new Set<Listener>();

/** Notify anything watching that a table changed. */
export function emit(): void {
  for (const listener of listeners) listener();
}

export function subscribe(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** Round-trip latency, so loading states are visible rather than theoretical. */
export function latency<T>(value: T, ms = 180): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(structuredClone(value)), ms));
}

export function nowIso(): string {
  return new Date().toISOString();
}
