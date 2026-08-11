"use client";

import type { ReactNode } from "react";
import { Loader2, Rocket } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogTitle,
} from "@/components/ui/dialog";

/**
 * The one action with no undo of any kind.
 *
 * Reject and even Delete only affect our own row; this hands the post to
 * Metricool, and from there it goes to a page with an audience on a schedule we
 * no longer own. The old app confirmed nothing — `Publish now` fired on the
 * click — and that is the one part of its shape not worth copying.
 *
 * `children` is where the time gets chosen when there is nowhere else to put
 * it. The drawer has a footer and puts `PublishAt` in it directly, the way the
 * old sheet did; the queue's row menu has no such surface, so it passes the
 * field in here.
 */
export function PublishDialog({
  open,
  onOpenChange,
  busy,
  onConfirm,
  children,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  busy: boolean;
  onConfirm: () => void;
  children?: ReactNode;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      {/* No `DialogDescription`: Radix warns when one is missing unless the
          content says outright that there isn't one. */}
      <DialogContent className="sm:max-w-md" aria-describedby={undefined}>
        <DialogTitle>Publish to Metricool?</DialogTitle>
        {children}
        <DialogFooter className="gap-2">
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button disabled={busy} onClick={onConfirm}>
            {busy ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <Rocket className="size-4" />
            )}
            Publish
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
