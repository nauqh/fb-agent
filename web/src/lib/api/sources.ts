import type { SourceItem } from "@/lib/types";
import type { Feed } from "@/lib/api/feeds";
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
  pageIds: number[],
  refresh = false,
): Promise<SourceItem[]> {
  return get<SourceItem[]>("/sources/competitors", {
    // An empty array sends no `page_ids` at all, which the server reads as
    // every Page. That is the shared pool: a competitor is configured under one
    // Page in Metricool — whichever had room under their 100-per-account cap —
    // and any Page assigned it can read its posts.
    ...(pageIds.length > 0 ? { page_ids: pageIds } : {}),
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

/** Mirrors `SourcesConfigOut` in api/app/routes/sources.py. */
export interface SourcesConfig {
  since_days: number;
  max_items: number;
  /** Rows, not file entries — see `api/feeds.ts`. Added and removed on Settings. */
  feeds: Feed[];
  lookback_days: number;
  grid_limit: number;
}

/**
 * What a run is configured with, read back from the server.
 *
 * Two halves from two places now: the windows are `config/sources.yml`, the
 * feeds are rows. Read rather than restated on this side, for the reason
 * `api/config.ts` records about `layout.yml` — Settings showing a hand-kept
 * copy of a config file is a screen that can disagree with the run it claims to
 * describe.
 */
export async function getSourcesConfig(pageId: number): Promise<SourcesConfig> {
  return get<SourcesConfig>("/sources/config", { page_id: pageId });
}

/** Mirrors `CompetitorOut`. `posts_stored: 0` is the row worth looking at. */
export interface CompetitorPage {
  /** Metricool's own row id — what DELETE takes. Null on rows they return
   *  without one, which is why removal is disabled rather than guessed. */
  id: number | null;
  provider_id: string;
  name: string;
  followers: number | null;
  /**
   * Facebook's CDN, signed and expiring in about four days.
   *
   * Safe to render only because this list is never stored — the server re-reads
   * it live on every request, so the URL reaching the browser is minutes old.
   * Storing it is what `routes/sources.VOLATILE` exists to undo for posts.
   */
  picture: string | null;
  posts_stored: number;
  /** Which of our Pages read this competitor. Empty means none have assigned it. */
  assigned_page_ids: number[];
  /** Whose Metricool set it sits in — where the 100-competitor allowance went. */
  page_id: number;
  page_name: string;
}

/**
 * The Page's competitor set, live from Metricool.
 *
 * A separate call from `getSourcesConfig` on purpose — that one is a local file
 * and cannot fail, this one is a vendor that has 502'd twice, and one request
 * for both would let Metricool being down blank the feed list as well.
 */
export async function getCompetitorPages(pageIds: number[] = []): Promise<CompetitorPage[]> {
  return get<CompetitorPage[]>("/sources/competitors/pages", {
    // Defaults to every Page, because the number that matters is the account
    // total: Metricool allows 100 competitors across the whole account, and
    // this is the only screen where that budget is visible.
    ...(pageIds.length > 0 ? { page_ids: pageIds } : {}),
  });
}
