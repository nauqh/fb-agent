import type { SourceItem } from "@/lib/types";
import {
  ARTICLE_FEED,
  FEED_FAILURES,
  TWEET_LOOKUP,
  type LiveSourceItem,
} from "@/lib/fixtures/sources";
import { db, emit, latency, nowIso } from "@/lib/store";

/**
 * `GET /sources/rivals|articles|tweet`, `POST /sources`.
 *
 * The rule this module enforces is **browsing does not write**. Rivals arrive
 * by Metricool sync and are rows already; articles and tweets are fetched live
 * and become rows only when ticked, which is what keeps `source_item` from
 * filling with hundreds of unread articles.
 */

export async function getRivals(pageId: number): Promise<SourceItem[]> {
  const rows = db.sourceItems
    .filter((item) => item.kind === "rival_post" && item.synced_for_page_id === pageId)
    // Reactions is the default sort on Rivals — it was in the old panel and it
    // is the only metric populated across effectively every rival row.
    .sort((a, b) => (b.reactions ?? 0) - (a.reactions ?? 0));
  return latency(rows, 420);
}

export interface ArticleFeedResult {
  items: LiveSourceItem[];
  /** Feeds that did not answer. A feed that rots goes unnoticed off-screen. */
  failures: { feed_url: string; error: string }[];
}

export async function getArticles(): Promise<ArticleFeedResult> {
  return latency({ items: ARTICLE_FEED, failures: FEED_FAILURES }, 620);
}

/** One tweet resolved from a pasted URL. Never a browsable list. */
export async function getTweet(url: string): Promise<LiveSourceItem> {
  const id = url.match(/status\/(\d+)/)?.[1];
  if (!id) {
    await latency(null, 200);
    throw new Error("That does not look like a tweet URL — expected .../status/<id>");
  }
  const tweet = TWEET_LOOKUP[id];
  if (!tweet) {
    await latency(null, 400);
    throw new Error(`x.com returned no tweet for id ${id}`);
  }
  return latency(tweet, 540);
}

/**
 * Persist ticked items.
 *
 * `UNIQUE (kind, external_id)` is enforced here rather than left to the caller:
 * ticking the same article twice returns the existing row instead of creating a
 * second one.
 */
export async function saveSources(items: LiveSourceItem[]): Promise<SourceItem[]> {
  const saved = items.map((item) => {
    const existing = db.sourceItems.find(
      (row) => row.kind === item.kind && row.external_id === item.external_id,
    );
    if (existing) return existing;

    const row: SourceItem = { ...item, id: db.nextSourceItemId++, created_at: nowIso() };
    db.sourceItems.push(row);
    return row;
  });

  emit();
  return latency(saved, 260);
}

/** Cart display: resolve the ids the client is holding back to rows. */
export async function getSourceItems(ids: number[]): Promise<SourceItem[]> {
  const rows = ids
    .map((id) => db.sourceItems.find((item) => item.id === id))
    .filter((item): item is SourceItem => item !== undefined);
  return latency(rows, 90);
}
