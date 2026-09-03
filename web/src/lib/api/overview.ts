import { del, get, post } from "@/lib/api/client";
import { asUtc } from "@/lib/format";
import type { Draft } from "@/lib/types";

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

/** The raw read. Not exported — `getPerformanceWindow` is the way in, and a
 *  caller reaching past it would get a window with no baseline to compare. */
async function getPerformance(pageId: number, days: number): Promise<PostStats[]> {
  return get<PostStats[]>("/overview/performance", { page_id: pageId, days });
}

/** A window of published posts, and the window immediately before it. */
export interface PerformanceWindow {
  /** Inside the window, best first — the server's sort, preserved. */
  posts: PostStats[];
  /** The `days` before that, for a comparison. Empty on a young Page. */
  previous: PostStats[];
}

/**
 * The window and its predecessor, from one read.
 *
 * The totals mean nothing without a baseline — "3.2M reach" is neither good nor
 * bad on its own — and Metricool's stats call takes a *number of days back*
 * rather than a range, so the previous window cannot be asked for separately:
 * `days=60` already contains the last 30. Reading `days * 2` and cutting at the
 * boundary is the only route to both halves, and it costs a doubled payload (a
 * 60-day window becomes ~870 rows on History Retraced).
 *
 * **The boundary is fixed here, at fetch time, not wherever the result is
 * rendered.** `Date.now()` during a render is impure — React's lint rule says
 * so and it is right: an unrelated re-render would silently move the cutoff and
 * a post could cross it between two paints.
 *
 * A post with no `published_at` counts as inside the window rather than being
 * dropped. It is a post the Page published, and hiding it because Metricool
 * sent no `created` would make the list disagree with the count above it.
 */
export async function getPerformanceWindow(
  pageId: number,
  days: number,
): Promise<PerformanceWindow> {
  const all = await getPerformance(pageId, days * 2);
  const cutoff = Date.now() - days * 86_400_000;
  const posts: PostStats[] = [];
  const previous: PostStats[] = [];
  for (const post of all) {
    const at = post.published_at === null ? null : asUtc(post.published_at).getTime();
    (at !== null && at < cutoff ? previous : posts).push(post);
  }
  return { posts, previous };
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

/**
 * Write this saved post's story again, from scratch.
 *
 * The same story, not a copy and not a style sample — it runs as a topic, so
 * the subject binds without the writer treating our own prose as an article to
 * summarise. Answers with draft ids to poll, like any other run.
 */
export async function reuseSaved(savedId: number): Promise<number[]> {
  return post<number[]>(`/overview/saved/${savedId}/reuse`, {});
}

/**
 * Put the original back in the queue — same caption, same picture.
 *
 * Distinct from `reuseSaved`, which writes the story again from scratch. This
 * answers 201 with the Draft it made rather than 202 with ids to poll: nothing
 * generates, so there is nothing to wait for. It can fail with 409 when the
 * original image has expired off Facebook's CDN, and that message is written to
 * be shown verbatim.
 */
export async function repostSaved(savedId: number): Promise<Draft> {
  return post<Draft>(`/overview/saved/${savedId}/repost`, {});
}

export async function unsavePost(savedId: number): Promise<void> {
  await del(`/overview/saved/${savedId}`);
}
