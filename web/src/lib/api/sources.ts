import type { SourceItem } from "@/lib/types";
import { get, post } from "@/lib/api/client";

/**
 * A Source Item that is not a row yet — no id, no created_at.
 *
 * It has a type of its own because **browsing does not write**: an article or
 * tweet is fetched live and shown in the grid long before, and usually without
 * ever, becoming a row. Mirrors `SourceItemBase` in api/app/models.py, which is
 * the shape `POST /sources` accepts and the three adapters return.
 */
export type LiveSourceItem = Omit<SourceItem, "id" | "created_at">;

/**
 * `GET /sources`, `/sources/rivals|articles|tweet`, `POST /sources`.
 *
 * The rule this module surfaces is **browsing does not write**. Rivals arrive
 * by Metricool sync and are rows already; articles and tweets are fetched live
 * and become rows only when ticked, which is what keeps `source_item` from
 * filling with hundreds of unread articles.
 *
 * The enforcement lives on the server — the API refuses an article that is not
 * from a curated feed — because this file is the client and cannot be the thing
 * that guarantees it.
 */

/** Rows, already synced. The server re-syncs from Metricool on each read. */
export async function getRivals(pageId: number): Promise<SourceItem[]> {
  return get<SourceItem[]>("/sources/rivals", { page_id: pageId });
}

export interface ArticleFeedResult {
  items: LiveSourceItem[];
  /** Feeds that did not answer. A feed that rots goes unnoticed off-screen. */
  failures: { feed_url: string; error: string }[];
}

export async function getArticles(): Promise<ArticleFeedResult> {
  return get<ArticleFeedResult>("/sources/articles");
}

/** One tweet resolved from a pasted URL. Never a browsable list. */
export async function getTweet(url: string): Promise<LiveSourceItem> {
  return get<LiveSourceItem>("/sources/tweet", { url });
}

/**
 * Persist ticked items.
 *
 * Idempotent by `UNIQUE (kind, external_id)` on the server: ticking the same
 * article twice returns the existing row rather than creating a second one.
 */
export async function saveSources(items: LiveSourceItem[]): Promise<SourceItem[]> {
  return post<SourceItem[]>("/sources", items);
}

/** Cart display: resolve the ids the client is holding back to rows. */
export async function getSourceItems(ids: number[]): Promise<SourceItem[]> {
  if (ids.length === 0) return [];
  return get<SourceItem[]>("/sources", { ids: ids.join(",") });
}
