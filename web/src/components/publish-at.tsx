"use client";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { pageLocalInput } from "@/lib/format";
import { cn } from "@/lib/utils";

/**
 * When the post should go out. Empty means as soon as Metricool will take it.
 *
 * The value is a naive stamp read in the *Page's* zone — `publication_date`
 * attaches `settings.timezone` to it server-side, and an offset suffix is what
 * Metricool rejects, which a `datetime-local` cannot produce anyway. The floor
 * is the Page's clock for the same reason: the browser's would let an operator
 * in Melbourne pick a time already past in Ho Chi Minh.
 *
 * The picker itself always offers the *operating system's* clock and no
 * attribute can change that, so the label carries the zone. One clock, GMT+7,
 * everywhere in this app — an operator abroad reads the same times the client
 * in Vietnam does, and no conversion appears anywhere to be misread as a second
 * standard.
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
    <div className={cn("space-y-1.5", className)}>
      <Label htmlFor="publish-when">Publish at (GMT+7)</Label>
      <Input
        id="publish-when"
        type="datetime-local"
        value={value}
        min={pageLocalInput()}
        onChange={(event) => onChange(event.target.value)}
      />
    </div>
  );
}
