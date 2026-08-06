"use client";

import { useRouter } from "next/navigation";

import { DraftDetail } from "@/components/draft-detail";
import { Sheet, SheetContent, SheetDescription, SheetTitle } from "@/components/ui/sheet";

/**
 * The draft, over the queue.
 *
 * Open is a route rather than a piece of state: being on `/review/12` *is* the
 * draft being open. That keeps every link deep-linkable, keeps the back button
 * meaning "close", and lets approving navigate to the next draft by pushing a
 * URL — which is what it already did when this was a pane.
 */
export function DraftSheet({ draftId }: { draftId: number }) {
  const router = useRouter();

  return (
    <Sheet
      open
      onOpenChange={(next) => {
        if (!next) router.push("/review");
      }}
    >
      <SheetContent className="sm:max-w-[min(96vw,1180px)]">
        <SheetTitle>Draft {draftId}</SheetTitle>
        <SheetDescription>Review and edit draft {draftId}.</SheetDescription>
        {/* The panel scrolls, not the page behind it. */}
        <div className="min-h-0 flex-1 overflow-y-auto px-6 py-6">
          <DraftDetail draftId={draftId} />
        </div>
      </SheetContent>
    </Sheet>
  );
}
