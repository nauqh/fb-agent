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

export function timeAgo(iso: string | null): string {
  if (!iso) return "—";
  const seconds = (Date.now() - new Date(iso).getTime()) / 1000;
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
  return iso ? stamp.format(new Date(iso)) : "—";
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
