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
export type SourceSort = "reactions" | "newest";

export async function getCompetitorPosts(
  pageIds: number[],
  refresh = false,
  sort: SourceSort = "reactions",
): Promise<SourceItem[]> {
  return get<SourceItem[]>("/sources/competitors", {
    // An empty array sends no `page_ids` at all, which the server reads as
    // every Page. That is the shared pool: a competitor is configured under one
    // Page in Metricool — whichever had room under their 100-per-account cap —
    // and any Page assigned it can read its posts.
    ...(pageIds.length > 0 ? { page_ids: pageIds } : {}),
    ...(refresh ? { refresh: "true" } : {}),
    sort,
  });
}

/** Mirrors `CompetitorReach`. Counts over rows we hold — no Metricool call. */
export interface CompetitorReach {
  /** Assignments for this Page. Zero means it is on the provenance fallback. */
  assigned: number;
  /** Posts that arrived through this Page's own Metricool set. */
  own_set_posts: number;
  /** Everything it may read, before the reactions window. Zero empties the grid. */
  visible_posts: number;
  /**
   * Distinct sources this Page has generated from — including ones off screen,
   * and ones it can no longer see at all. Counted from its drafts, not the pool.
   */
  used_posts: number;
}

/**
 * What the grid is not showing: why it is empty, and how much it is hiding.
 *
 * "Nobody is configured", "nothing has been synced" and "quiet week" are one
 * blank screen otherwise, and the operator's next move differs for each. Five of
 * the ten Pages have zero competitors in Metricool — including one of the Pages
 * the client's 2026-08-16 note was about — and the grid said nothing at all.
 *
 * `used_posts` is the same failure in the non-empty case: the marker is computed
 * over the 60 rows returned, so a post generated from yesterday has usually
 * fallen out of the window along with any sign it was used.
 */
export async function getCompetitorReach(pageIds: number[]): Promise<CompetitorReach> {
  return get<CompetitorReach>("/sources/competitors/reach", {
    ...(pageIds.length > 0 ? { page_ids: pageIds } : {}),
  });
}

/**
 * One stored Source Item by id — what a Draft was generated from.
 *
 * The review drawer's only way to answer "which post did this come from".
 * `Draft.source_item_id` has always been on the wire and nothing rendered it,
 * which is exactly what the client reported on 2026-08-16.
 *
 * A second request rather than a field on the Draft: see `get_source_item` in
 * api/app/routes/sources.py for why the Draft response cannot carry it.
 */
export async function getSourceItem(itemId: number): Promise<SourceItem> {
  return get<SourceItem>(`/sources/items/${itemId}`);
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
  /**
   * Whether `page_id` reads this without an assignment, through the fallback.
   *
   * The screen cannot derive this: a Page switches to assignment-only as soon as
   * it has *any* assignment, which may be on a different competitor entirely.
   * Empty `assigned_page_ids` therefore means "nobody reads it" or "the Page it
   * sits under reads it by default", and only the server can tell which.
   */
  reads_by_default: boolean;
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
