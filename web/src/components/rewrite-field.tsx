"use client";

import { useState } from "react";
import { Loader2, RefreshCw } from "lucide-react";
import { toast } from "sonner";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

/**
 * Ask the writer for one field again, optionally saying how.
 *
 * Sits directly above its own field rather than in the footer, because it acts
 * on *this* field and a row of three identical buttons somewhere else would not
 * say which. The old app put it in the same place
 * (`regenerate-field-control.tsx`).
 *
 * **The box is always visible, not behind a toggle.** The client asked for it in
 * as many words - *"should there be a textbox for me to input how I want it to
 * be changed"* - after pressing the unargued button on a hook that was too short
 * and getting another short hook. Nothing in `validators.py` sets a minimum
 * length, so the button alone can only re-roll, never steer; a control hidden
 * behind a chevron would leave them pressing the same button. Empty is the
 * common case and is still one click.
 *
 * **Writes nothing.** `ask` sends what is on screen and puts the answer in the
 * box; saving is the screen's own button. Shared by the review drawer and No
 * source, which has no draft yet (client, 2026-10-21).
 */
export function Regenerate({
  label,
  empty = false,
  ask,
}: {
  label: string;
  /** The field has no text, so the press writes one rather than rewriting. */
  empty?: boolean;
  ask: (instruction: string | undefined) => Promise<void>;
}) {
  const [busy, setBusy] = useState(false);
  // Kept after a press, not cleared: "make it longer" is usually said twice, and
  // the box is on screen, so nothing is being reused invisibly. It is never sent
  // to the row - an instruction describes an action, not the post.
  const [instruction, setInstruction] = useState("");
  const name = label.toLowerCase();

  async function run() {
    setBusy(true);
    try {
      await ask(instruction.trim() || undefined);
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "Could not rewrite that");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex items-center gap-2">
      <Input
        value={instruction}
        disabled={busy}
        placeholder={
          empty ? `What should the ${name} say? Optional.` : `How should the ${name} change? Optional.`
        }
        onChange={(event) => setInstruction(event.target.value)}
        // Enter runs it. The box is one line and has no other action, and the
        // form below is saved by its own button, so nothing else can be
        // submitted by accident.
        onKeyDown={(event) => {
          if (event.key === "Enter") {
            event.preventDefault();
            void run();
          }
        }}
        maxLength={500}
        className="h-7 text-xs"
      />
      <button
        type="button"
        onClick={() => void run()}
        disabled={busy}
        title={
          empty
            ? `Have the writer write the ${name} from the other fields.`
            : `Ask the writer for a new ${name}, keeping the other fields.`
        }
        className="inline-flex shrink-0 items-center gap-1 rounded px-1.5 py-1 text-[11px] font-normal text-muted-foreground transition-colors hover:bg-muted hover:text-foreground disabled:opacity-50"
      >
        {busy ? (
          <Loader2 className="size-3 animate-spin" />
        ) : (
          <RefreshCw className="size-3" />
        )}
        {empty ? "Write" : "Rewrite"}
      </button>
    </div>
  );
}

export function Field({
  label,
  hint,
  flagged,
  regenerate,
  children,
}: {
  label: string;
  hint?: string;
  flagged?: boolean;
  /** Ask the writer for this field again. Absent on fields it cannot rewrite. */
  regenerate?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-2">
      <div className="flex items-baseline justify-between gap-3">
        <Label className="text-sm">{label}</Label>
        {hint ? (
          <span
            className={cn(
              "text-[11px] tabular-nums",
              flagged ? "text-destructive" : "text-muted-foreground",
            )}
          >
            {hint}
          </span>
        ) : null}
      </div>
      {/* Its own row, between the label and the box it rewrites. It used to be a
          word inside the `<Label>`, which left nowhere for the prompt input to
          go - and an `<input>` inside a `<label>` steals the click that should
          focus the field. */}
      {regenerate}
      {children}
    </div>
  );
}
