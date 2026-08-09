/**
 * Timestamps render in the Page's zone, not the browser's — an operator
 * elsewhere must read the same clock the posting schedule is written against.
 */
const PAGE_TIMEZONE = "Asia/Ho_Chi_Minh";

const relative = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
const compact = new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 });
const stamp = new Intl.DateTimeFormat("en-GB", {
  timeZone: PAGE_TIMEZONE,
  dateStyle: "medium",
  timeStyle: "short",
});

/**
 * The columns are `timestamp without time zone`, so the API returns
 * `2026-08-06T15:22:48`
 * with no offset and `new Date()` reads it as *local* time. Everything the API
 * writes is UTC, so say so — without this a draft made a minute ago showed as
 * "10 hours ago" on a UTC+7 machine.
 */
export function asUtc(iso: string): Date {
  return new Date(/(?:Z|[+-]\d{2}:?\d{2})$/.test(iso) ? iso : `${iso}Z`);
}

export function timeAgo(iso: string | null): string {
  if (!iso) return "—";
  const seconds = (Date.now() - asUtc(iso).getTime()) / 1000;
  const units: [Intl.RelativeTimeFormatUnit, number][] = [
    ["minute", 60],
    ["hour", 3_600],
    ["day", 86_400],
    ["week", 604_800],
  ];
  if (seconds < 60) return "just now";
  let chosen: [Intl.RelativeTimeFormatUnit, number] = units[0];
  for (const unit of units) if (seconds >= unit[1]) chosen = unit;
  return relative.format(-Math.round(seconds / chosen[1]), chosen[0]);
}

/**
 * `4 Aug 2026, 14:30`, in the Page's timezone rather than the browser's.
 *
 * `timeAgo` is for the grid, where "2 days ago" is the only thing being asked.
 * This is for the detail view, where an operator deciding whether a story is
 * stale needs the actual instant — and needs it in the same zone the posting
 * schedule is written against.
 */
export function fullDate(iso: string | null): string {
  return iso ? stamp.format(asUtc(iso)) : "—";
}

export function metric(value: number | null): string {
  return value === null ? "—" : compact.format(value);
}

export function chars(value: string | null | undefined): string {
  return `${(value?.length ?? 0).toLocaleString()} chars`;
}

export function words(value: string | null | undefined): number {
  return value?.trim() ? value.trim().split(/\s+/).length : 0;
}

const dayKeyStamp = new Intl.DateTimeFormat("en-CA", {
  timeZone: PAGE_TIMEZONE,
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
});
const dayHeadingStamp = new Intl.DateTimeFormat("en-GB", {
  timeZone: PAGE_TIMEZONE,
  weekday: "long",
  day: "numeric",
  month: "short",
});
const timeStamp = new Intl.DateTimeFormat("en-GB", {
  timeZone: PAGE_TIMEZONE,
  timeStyle: "short",
});

/**
 * `2026-08-08` in the Page's zone — the key rows are grouped by.
 *
 * The zone matters more here than anywhere else on the screen. Grouping on the
 * browser's day would put a draft made at 06:00 in Ho Chi Minh City under the
 * previous date for anyone in Europe, so the same queue would break into
 * different days depending on who opened it.
 */
export function dayKey(iso: string): string {
  return dayKeyStamp.format(asUtc(iso));
}

/** `Today`, `Yesterday`, or `Friday, 7 Aug`. */
export function dayHeading(iso: string): string {
  const day = dayKey(iso);
  const now = Date.now();
  if (day === dayKeyStamp.format(new Date(now))) return "Today";
  if (day === dayKeyStamp.format(new Date(now - 86_400_000))) return "Yesterday";
  return dayHeadingStamp.format(asUtc(iso));
}

/** `14:30`. For a row whose date is already stated by its group heading. */
export function timeOfDay(iso: string | null): string {
  return iso ? timeStamp.format(asUtc(iso)) : "—";
}
