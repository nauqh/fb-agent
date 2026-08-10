/**
 * Where a Page's logo comes from, in order of trust.
 *
 * 1. `avatar_image_path` — a file committed under `api/assets/`. Cannot 404,
 *    and it is the artwork someone actually made. Two Pages have one.
 * 2. `avatar_url` — what Metricool serves for the brand. `static.metricool.com`,
 *    with no expiry signature, unlike the Facebook CDN URLs beside it in the
 *    same payload. This is what stops the other eight rendering as a letter.
 * 3. Nothing, and the caller draws an initial.
 *
 * Not used for the watermark. That is stamped into published images and must be
 * a committed file — see `Page.watermark_image_path`, and the months the old
 * app spent printing its page name as text after a bucket was cleared.
 */
export function pageAvatar(page: {
  avatar_image_path?: string | null;
  avatar_url?: string | null;
}): string | null {
  if (page.avatar_image_path) return `/api/${page.avatar_image_path}`;
  return page.avatar_url ?? null;
}

/**
 * The same choice, without the `/api/` prefix.
 *
 * `PageBadge` renders both kinds and decides the prefix itself — it is used in
 * the queue and in the draft sheet, where the value has always been a bare
 * stored path. Two functions rather than a flag: the caller knows which shape
 * it wants and a boolean argument at the call site would not say which.
 */
export function pageAvatarRaw(page: {
  avatar_image_path?: string | null;
  avatar_url?: string | null;
}): string | null {
  return page.avatar_image_path ?? page.avatar_url ?? null;
}
