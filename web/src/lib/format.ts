/**
 * Timestamps render in the Page's zone, not the browser's — an operator
 * elsewhere must read the same clock the posting schedule is written against.
 */
export const PAGE_TIMEZONE = "Asia/Ho_Chi_Minh";

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

/**
 * Now, as `<input type="datetime-local">` spells it, in the *Page's* zone.
 *
 * The input has no timezone of its own — it hands back a naive
 * `2026-08-14T18:00`, and the API reads that as the Page's local time
 * (`publish/metricool.py:119` attaches `settings.timezone` to a naive value).
 * So the field's floor has to be the Page's clock too. Using the browser's
 * would let an operator on UTC pick a time already past in Ho Chi Minh, which
 * Metricool rejects.
 *
 * `sv-SE` is the shortest route to `YYYY-MM-DD HH:mm` from `Intl`; the space
 * becomes the `T` the input wants.
 */
const localInput = new Intl.DateTimeFormat("sv-SE", {
  timeZone: PAGE_TIMEZONE,
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

export function pageLocalInput(date: Date = new Date()): string {
  return localInput.format(date).replace(" ", "T");
}

/**
 * There is deliberately nothing here that converts *out* of the Page's zone.
 *
 * The operator is in Melbourne and the client is in Vietnam; one clock, GMT+7,
 * is the whole point. A helper that renders an instant in the browser's zone
 * would be used, and the second clock beside the first is what makes a schedule
 * misread.
 */

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

/**
 * What day it is *on the Page's clock* — `2026-08-11`.
 *
 * Not `new Date().toISOString().slice(0, 10)` and not the browser's date
 * either. Metricool's planner stamps are naive local time in the Page's zone,
 * so "today" has to be asked in that zone or the two disagree for three hours
 * every night: at 00:30 in Melbourne it is still the previous day in Ho Chi
 * Minh, and the schedule grid highlighted tomorrow.
 */
export function pageToday(): string {
  return dayKeyStamp.format(new Date());
}

/**
 * A `Date` at *local* noon on the Page's current date.
 *
 * Day arithmetic (`setDate`, `getDay`) reads the browser's calendar, so it
 * needs a Date whose browser-local date is the Page's date. Noon leaves twelve
 * hours of slack either side, which no offset can cross.
 */
export function pageNoon(): Date {
  return new Date(`${pageToday()}T12:00:00`);
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
