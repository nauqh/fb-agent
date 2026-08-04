/**
 * Quota is counted per calendar day in Asia/Ho_Chi_Minh, not in the browser's
 * timezone — an operator in another zone must see the same number the Page's
 * policy is written against.
 */
const PAGE_TIMEZONE = "Asia/Ho_Chi_Minh";

const dayFormatter = new Intl.DateTimeFormat("en-CA", {
  timeZone: PAGE_TIMEZONE,
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
});

/** `2026-08-03` for an instant, as that date falls in Asia/Ho_Chi_Minh. */
export function pageDay(iso: string | Date): string {
  return dayFormatter.format(typeof iso === "string" ? new Date(iso) : iso);
}

export function isTodayInHoChiMinh(iso: string): boolean {
  return pageDay(iso) === pageDay(new Date());
}
