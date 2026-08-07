"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { DraftDetail } from "@/components/draft-detail";
import { Drawer, DrawerContent, DrawerDescription, DrawerTitle } from "@/components/ui/drawer";

/** Matches the `duration-300` on the panel. */
const CLOSE_MS = 300;

/**
 * The draft, over the queue.
 *
 * Open is a route rather than a piece of state: being on `/review/12` *is* the
 * draft being open. That keeps every link deep-linkable, keeps the back button
 * meaning "close", and lets approving navigate to the next draft by pushing a
 * URL — which is what it already did when this was a pane.
 *
 * The one thing a route cannot do on its own is animate *out*. Navigating away
 * unmounts this component immediately, so Radix never gets to run the closing
 * animation and the drawer vanished. `closing` holds it on screen for exactly
 * as long as the transition lasts, and the navigation happens after.
 */
export function DraftSheet({ draftId }: { draftId: number }) {
  const router = useRouter();
  const [closing, setClosing] = useState(false);

  /** Slide out, then navigate. Shared so a decision closes the same way a
   *  dismissal does — approving used to jump straight to the next draft's URL,
   *  which swapped the contents underneath an open drawer. */
  function close() {
    if (closing) return;
    setClosing(true);
    setTimeout(() => router.push("/review"), CLOSE_MS);
  }

  return (
    <Drawer
      open={!closing}
      onOpenChange={(next) => {
        if (!next) close();
      }}
    >
      <DrawerContent>
        <DrawerTitle>Draft {draftId}</DrawerTitle>
        <DrawerDescription>Review and edit draft {draftId}.</DrawerDescription>
        {/* The drawer scrolls, not the page behind it. */}
        <div className="min-h-0 flex-1 overflow-y-auto px-7 py-6">
          <DraftDetail draftId={draftId} onDecided={close} />
        </div>
      </DrawerContent>
    </Drawer>
  );
}
