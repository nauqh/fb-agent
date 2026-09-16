"use client";

import type { Page } from "@/lib/types";

export type InsetSource = Page["inset_source"];

/**
 * Which search a run's Find inset uses, beside the checkbox that turns it on.
 *
 * Starts on the Page's own choice (Settings, Inset pictures) and is only an
 * override for this run (client, 2026-09-16): a history Page set to Google
 * still has the odd post that wants a stock photo. Callers hold `null` for "not
 * touched" and resolve it against the Page, so switching Page moves the default
 * with it instead of carrying the last Page's choice across.
 *
 * A native select, like the post style beside it in the dock: two options, one
 * row of height, and nothing a custom control would add.
 */
export function InsetSourceSelect({
  value,
  onChange,
}: {
  value: InsetSource;
  onChange: (next: InsetSource) => void;
}) {
  return (
    <select
      value={value}
      onChange={(event) => onChange(event.target.value as InsetSource)}
      aria-label="Where Find inset searches"
      className="h-7 shrink-0 rounded-md border bg-card px-1.5 text-xs text-muted-foreground"
    >
      <option value="google">Google</option>
      <option value="unsplash">Unsplash</option>
    </select>
  );
}
