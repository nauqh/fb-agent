import type { SourceItem } from "@/lib/types";
import { get } from "@/lib/api/client";

/**
 * A Source Item that is not a row yet — no id, no created_at.
 *
 * It has a type of its own because **browsing does not write**: an RSS item or
 * tweet is fetched live and shown in the grid long before, and usually without
 * ever, becoming a row. Mirrors `SourceItemBase` in api/app/models.py, which is
 * the shape `POST /generate` accepts and the three adapters return.
 */
export type LiveSourceItem = Omit<SourceItem, "id" | "created_at">;

/**
 * `GET /sources/competitors|rss|tweet`. Reads only.
 *
 * **Browsing does not write.** There is no save here any more: the Cart carries
 * the items and `POST /generate` writes the ones a run actually uses, so
 * nothing is stored that is not used. See docs/plan.md, "Ticking stops
 * writing".
 */

/**
 * Stored competitor posts.
 *
 * `refresh` forces a Metricool sync. Without it the server answers from what it
 * already has, because a sync costs ~5.5s and 1.6MB to fetch 500 posts against
 * a seven-day window that gains roughly three an hour — so syncing on every tab
 * open paid six seconds to learn nothing. The server still syncs by itself when
 * it has nothing stored.
 */
export async function getCompetitorPosts(
  pageId: number,
  refresh = false,
): Promise<SourceItem[]> {
  return get<SourceItem[]>("/sources/competitors", {
    page_id: pageId,
    ...(refresh ? { refresh: "true" } : {}),
  });
}

export interface RssFeedResult {
  items: LiveSourceItem[];
  /** Feeds that did not answer. A feed that rots goes unnoticed off-screen. */
  failures: { feed_url: string; error: string }[];
}

/** The Page's curated feeds. Per-page: the beats do not overlap. */
export async function getRss(pageId: number): Promise<RssFeedResult> {
  return get<RssFeedResult>("/sources/rss", { page_id: pageId });
}

/** One tweet resolved from a pasted URL. Never a browsable list. */
export async function getTweet(url: string): Promise<LiveSourceItem> {
  return get<LiveSourceItem>("/sources/tweet", { url });
}
