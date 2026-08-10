import { del, get, post } from "./client";

/**
 * A Page's RSS feeds. Rows, not configuration.
 *
 * They were `config/sources.yml` until the API started running from a container
 * image: a file written into one is gone at the next deploy, so the list an
 * operator has to change could not stay a file.
 */
export interface Feed {
  id: number;
  page_id: number;
  name: string;
  url: string;
  /** Why this feed earns its place — item count, summary length, images. */
  note: string | null;
  created_at: string;
}

/** What the server measured before it would write the row. */
export interface FeedProbe {
  items: number;
  with_images: number;
  median_summary: number;
  /** Age of the newest item. Null when no item carries a date. */
  newest_hours: number | null;
}

export async function getFeeds(pageId: number): Promise<Feed[]> {
  return get<Feed[]>("/feeds", { page_id: pageId });
}

/**
 * Add a feed. The server probes it first and refuses one that does not answer,
 * does not parse, or parses to nothing — so a 422 here is the feed's fault and
 * its message is written to be shown as-is.
 */
export async function addFeed(input: {
  page_id: number;
  name: string;
  url: string;
  note?: string;
}): Promise<{ feed: Feed; probe: FeedProbe | null }> {
  return post<{ feed: Feed; probe: FeedProbe | null }>("/feeds", input);
}

/** Changes tomorrow's grid and nothing already published — no row points at a feed. */
export async function removeFeed(feedId: number): Promise<void> {
  await del(`/feeds/${feedId}`);
}
