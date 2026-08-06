"use client";

import { useRouter } from "next/navigation";

import { DraftDetail } from "@/components/draft-detail";
import { Drawer, DrawerContent, DrawerDescription, DrawerTitle } from "@/components/ui/drawer";

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
    <Drawer
      open
      onOpenChange={(next) => {
        if (!next) router.push("/review");
      }}
    >
      <DrawerContent>
        <DrawerTitle>Draft {draftId}</DrawerTitle>
        <DrawerDescription>Review and edit draft {draftId}.</DrawerDescription>
        {/* The drawer scrolls, not the page behind it. Centred, so the content
            does not stretch to absurd line lengths on a wide monitor. */}
        <div className="min-h-0 flex-1 overflow-y-auto">
          <div className="mx-auto w-full max-w-[1400px] px-8 py-6">
            <DraftDetail draftId={draftId} />
          </div>
        </div>
      </DrawerContent>
    </Drawer>
  );
}
