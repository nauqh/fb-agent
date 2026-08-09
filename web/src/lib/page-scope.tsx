"use client";

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
} from "react";

import { listPages } from "@/lib/api/pages";
import { PAGE_COOKIE } from "@/lib/page-cookie";
import type { Page } from "@/lib/types";
import { useQuery } from "@/lib/use-query";

/**
 * Which Page every screen is looking at.
 *
 * Lives above the router, beside the Cart, so switching screens does not reset
 * it. One choice for the whole app rather than one per screen: the alternative
 * lets Review show History Retraced while the Cart generates for The Fact Feed,
 * which is a mistake nobody notices until the draft appears under the wrong
 * logo.
 *
 * The Pages are fetched **here and once**. Four components used to call
 * `listPages()` for themselves and take `pages[0]`, which was correct only
 * while there was one row — with two, `[0]` means "whichever sorts first by
 * name", so inserting a Page called Bible Focus would have moved every screen
 * onto it without one line changing.
 */

interface PageScopeValue {
  /** Every Page, in the order the API returned them (by name). */
  pages: Page[];
  /** The selected Page. Null only before the first fetch lands. */
  page: Page | null;
  /**
   * The selected Page's id, or null while unresolved.
   *
   * Screens pass this straight into their queries *and* their dep arrays. It
   * is deliberately null rather than a guessed 1 during the first render, so a
   * query cannot fire against the wrong Page and then correct itself — the
   * screens gate on `enabled` instead.
   */
  pageId: number | null;
  select: (id: number) => void;
}

const PageScopeContext = createContext<PageScopeValue | null>(null);

export function PageScopeProvider({
  /** From the cookie, read by the root layout so the first paint is right. */
  defaultPageId,
  children,
}: {
  defaultPageId: number | null;
  children: React.ReactNode;
}) {
  const [selected, setSelected] = useState<number | null>(defaultPageId);

  const { data: pages } = useQuery(() => listPages(), []);

  const select = useCallback((id: number) => {
    setSelected(id);
    // A year, path-wide, matching the sidebar's cookie. No `secure` — this is
    // served over http on the laptop.
    document.cookie = `${PAGE_COOKIE}=${id}; path=/; max-age=31536000; samesite=lax`;
  }, []);

  const value = useMemo<PageScopeValue>(() => {
    const all = pages ?? [];
    // The cookie can name a Page that no longer exists — the database is
    // delete-and-reseed by convention, so ids do move. Falling back to the
    // first Page is what keeps a stale cookie from emptying every screen.
    const page = all.find((candidate) => candidate.id === selected) ?? all[0] ?? null;
    return { pages: all, page, pageId: page?.id ?? null, select };
  }, [pages, selected, select]);

  return (
    <PageScopeContext.Provider value={value}>{children}</PageScopeContext.Provider>
  );
}

export function usePageScope(): PageScopeValue {
  const value = useContext(PageScopeContext);
  if (!value) {
    throw new Error("usePageScope must be used inside PageScopeProvider");
  }
  return value;
}
