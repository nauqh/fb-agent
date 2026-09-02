import { cn } from "@/lib/utils";

/**
 * A styled native `<select>`. The app has no Radix select; for a handful of
 * fixed options (trim seconds, the CTA pick) the native control is honest —
 * it gets keyboard, focus and a usable popup for free, and it matches the
 * input's height and border.
 */
export function NativeSelect({
  value,
  onValueChange,
  children,
  className,
  id,
  ariaLabel,
}: {
  value: string;
  onValueChange: (value: string) => void;
  children: React.ReactNode;
  className?: string;
  id?: string;
  ariaLabel?: string;
}) {
  return (
    <select
      id={id}
      aria-label={ariaLabel}
      value={value}
      onChange={(event) => onValueChange(event.target.value)}
      className={cn(
        "h-8 cursor-pointer appearance-none rounded-md border bg-background px-2 text-sm outline-none",
        "focus-visible:ring-2 focus-visible:ring-ring",
        className,
      )}
    >
      {children}
    </select>
  );
}

export function NativeSelectOption({
  value,
  children,
}: {
  value: string;
  children: React.ReactNode;
}) {
  return (
    <option value={value} className="bg-background text-foreground">
      {children}
    </option>
  );
}