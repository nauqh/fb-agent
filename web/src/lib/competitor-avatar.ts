/**
 * A competitor's logo, from their Facebook page id alone.
 *
 * Metricool also returns a `picture`, and `getCompetitorPages` carries it — but
 * that URL is Facebook's CDN, signed, expiring in about four days. It is only
 * safe to render because that list is read live on every request and never
 * stored (see `CompetitorMark`). Anywhere the competitor came from *our*
 * database — an assignment row, a stored post — there is no live list to take a
 * picture from, and the vendor call that would fetch one costs a request per
 * Page.
 *
 * Graph's public picture endpoint needs neither. `competitor_page_id` is the
 * Facebook page id, which is the same value the rows already link to, and the
 * endpoint 302s to a current image with no token. Verified 2026-09-06 against
 * three of the account's competitors: `200 image/jpeg`, 1.3–1.8KB at width 64.
 *
 * Nothing here can fail loudly: `CompetitorMark` falls back to an initial on
 * `onError`, which is what a private or deleted page will produce.
 */
export function competitorAvatar(competitorPageId: string | null): string | null {
  if (!competitorPageId) return null;
  // `width` rather than `height`: square crops are what the mark renders, and
  // 64 is the 32px slot at 2x.
  return `https://graph.facebook.com/${competitorPageId}/picture?type=square&width=64`;
}
