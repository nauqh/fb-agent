const relative = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
const compact = new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 });

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

export function metric(value: number | null): string {
  return value === null ? "—" : compact.format(value);
}

export function chars(value: string | null | undefined): string {
  return `${(value?.length ?? 0).toLocaleString()} chars`;
}

export function words(value: string | null | undefined): number {
  return value?.trim() ? value.trim().split(/\s+/).length : 0;
}
