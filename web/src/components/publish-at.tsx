"use client";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { pageLocalInput } from "@/lib/format";
import { cn } from "@/lib/utils";

/**
 * When the post should go out, on the Page's clock.
 *
 * The value is a naive stamp read as Asia/Ho_Chi_Minh — `publication_date`
 * attaches `settings.timezone` to it server-side, and an offset suffix is what
 * Metricool rejects, which a `datetime-local` cannot produce anyway. The floor
 * is the Page's clock for the same reason: the browser's would let an operator
 * in Melbourne pick a time already past in Ho Chi Minh.
 *
 * It is never empty. The picker's own default is the *operating system's* clock
 * and no attribute reaches it — an operator in Melbourne opening it saw their
 * own hour, which is not the hour the post goes out. Seeding the field means
 * the number on screen is always the Page's, and the picker opens on it rather
 * than on the machine's. `GMT+7` sits beside it because the field itself cannot
 * say so.
 *
 * Publishing immediately is this field left alone: `pageLocalSoon()` is already
 * a couple of minutes out, and the server clamps anything earlier than
 * `now + MIN_MINUTES_AHEAD` up to it anyway (`publish/metricool.py:120`), so a
 * stamp that goes stale while the operator reads the post cannot be rejected.
 */
export function PublishAt({
  value,
  onChange,
  className,
}: {
  value: string;
  onChange: (value: string) => void;
  className?: string;
}) {
  return (
    <div className={cn("flex items-center gap-1.5", className)}>
      <Label htmlFor="publish-when" className="sr-only">
        Publish at, Ho Chi Minh time
      </Label>
      <Input
        id="publish-when"
        type="datetime-local"
        value={value}
        min={pageLocalInput()}
        onChange={(event) => onChange(event.target.value)}
        // 28px, which is what `size="sm"` buttons measure — `h-8` left the
        // field one notch taller than everything beside it in the footer.
        className="h-7 w-auto text-xs"
      />
      <span className="text-xs text-muted-foreground">GMT+7</span>
    </div>
  );
}
