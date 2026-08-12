import { del, get, post } from "@/lib/api/client";

/**
 * Post performance, and the posts kept from it.
 *
 * Two halves that look alike and are not. Performance is read live from
 * Metricool and stored nowhere — their numbers move every day as Facebook's
 * counts catch up, and a local copy could only be stale. A saved post is a
 * decision, and needs a row precisely because Metricool's stats take a date
 * range: an old post is in no read at all.
 */
export interface PostStats {
  post_id: string;
  text: string;
  permalink_url: string | null;
  picture_url: string | null;
  published_at: string | null;
  reactions: number;
  comments: number;
  shares: number;
  clicks: number;
  impressions: number;
  /** reactions + comments + shares, computed on the server — Metricool's own
   *  `engagement` field is null on every row. */
  engagement: number;
  saved: boolean;
}

export interface SavedPost {
  id: number;
  page_id: number;
  metricool_post_id: string;
  text: string;
  permalink_url: string | null;
  picture_url: string | null;
  published_at: string | null;
  reactions: number;
  comments: number;
  shares: number;
  impressions: number;
  note: string | null;
  created_at: string;
}

export async function getPerformance(pageId: number, days = 90): Promise<PostStats[]> {
  return get<PostStats[]>("/overview/performance", { page_id: pageId, days });
}

export async function listSaved(pageId: number): Promise<SavedPost[]> {
  return get<SavedPost[]>("/overview/saved", { page_id: pageId });
}

/**
 * Keep a post. The metrics travel with it deliberately — they are a snapshot of
 * what it scored when saved, not a live figure, and re-reading them later would
 * need the post to still be inside a window it has by definition left.
 */
export async function savePost(pageId: number, post_: PostStats): Promise<SavedPost> {
  return post<SavedPost>("/overview/saved", {
    page_id: pageId,
    post_id: post_.post_id,
    text: post_.text,
    permalink_url: post_.permalink_url,
    picture_url: post_.picture_url,
    published_at: post_.published_at,
    reactions: post_.reactions,
    comments: post_.comments,
    shares: post_.shares,
    impressions: post_.impressions,
  });
}

export async function unsavePost(savedId: number): Promise<void> {
  await del(`/overview/saved/${savedId}`);
}
