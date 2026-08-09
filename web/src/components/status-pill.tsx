import { cn } from "@/lib/utils";

/**
 * One status, as a tinted tag with a saturated dot.
 *
 * The history here is worth keeping, because two obvious designs have already
 * failed. A flat 600 fill with white type was simply the colour it claimed to
 * be, but a queue is mostly one status, so a column of solid slabs became the
 * texture of the whole screen. A plain tint on its own went the other way — an
 * alpha wash and a pale 50/800 pair both read as *nearly* a colour rather than
 * as green.
 *
 * The dot is what makes the tint work. It is the full 500 with nothing over it,
 * so the hue is stated at full strength in 6px and the surface is free to stay
 * light. Colour and weight stop being the same dial.
 *
 * Colour is still spent only where it earns attention. `approved` and
 * `published` are the end states worth seeing; `failed` and `error` lost work.
 * Pending, rejected and draft stay grey — they are the background hum of the
 * queue, not events.
 *
 * Shared by the Review queue and the Schedule so the two cannot drift into
 * different ideas of what a status looks like, which is exactly what had
 * happened: one solid red, the other a tinted outline.
 */

export type StatusTone = "neutral" | "positive" | "negative" | "busy";

const TONE: Record<StatusTone, { pill: string; dot: string }> = {
  neutral: {
    pill: "border-border bg-muted text-muted-foreground",
    dot: "bg-muted-foreground/40",
  },
  positive: {
    pill: "border-green-600/25 bg-green-500/10 text-green-700 dark:text-green-400",
    dot: "bg-green-500",
  },
  negative: {
    pill: "border-red-600/25 bg-red-500/10 text-red-700 dark:text-red-400",
    dot: "bg-red-500",
  },
  busy: {
    // The one that is still moving, so its dot pulses like the rail's own.
    pill: "border-gold/40 bg-gold/10 text-amber-700 dark:text-amber-400",
    dot: "bg-gold animate-pulse",
  },
};

export function StatusPill({
  tone,
  label,
  className,
}: {
  tone: StatusTone;
  label: string;
  className?: string;
}) {
  const { pill, dot } = TONE[tone];

  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center gap-1.5 rounded-full border px-2 py-0.5",
        "text-xs font-medium",
        pill,
        className,
      )}
    >
      <span className={cn("size-1.5 shrink-0 rounded-full", dot)} aria-hidden />
      {label}
    </span>
  );
}
