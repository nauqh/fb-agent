/**
 * A Page's logo. Metricool's, with a committed file as the fallback.
 *
 * This order used to be the other way round, on the argument that a committed
 * asset cannot 404. That argument belongs to the *watermark* — drawn into
 * published images, where a missing file degrades silently and the old system
 * printed page names for months without one failed post. An avatar is UI
 * chrome: when it fails you see a letter, which announces itself.
 *
 * So Metricool wins, and the reason is not convenience. Their copy is the
 * Facebook profile picture, which is what this is documented to be, and it
 * **follows the page**: change the picture on Facebook and the app follows,
 * where a committed PNG goes stale with nobody noticing. Compared before
 * switching — their History Retraced logo is the same wordmark as the committed
 * one, 200px against 237px, which is well above the 32px it renders at.
 *
 * `avatar_image_path` stays as the fallback for a Page that has artwork but no
 * Metricool brand, and for a fresh database before the import has run.
 */
export function pageAvatar(page: {
  avatar_image_path?: string | null;
  avatar_url?: string | null;
}): string | null {
  if (page.avatar_url) return page.avatar_url;
  return page.avatar_image_path ? `/api/${page.avatar_image_path}` : null;
}

/** The same choice, unprefixed — `PageBadge` decides its own prefix. */
export function pageAvatarRaw(page: {
  avatar_image_path?: string | null;
  avatar_url?: string | null;
}): string | null {
  return page.avatar_url ?? page.avatar_image_path ?? null;
}
