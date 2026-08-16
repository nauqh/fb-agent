"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { DraftDetail } from "@/components/draft-detail";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogTitle } from "@/components/ui/dialog";
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

  /**
   * Whether the editor has text that is not in the database yet.
   *
   * A ref written by `DraftDetail`, so a keystroke does not re-render this.
   * Read only here, at the one moment it matters.
   */
  const dirty = useRef(false);
  const [confirming, setConfirming] = useState(false);

  /** Slide out, then navigate. Shared so a decision closes the same way a
   *  dismissal does — approving used to jump straight to the next draft's URL,
   *  which swapped the contents underneath an open drawer. */
  function close() {
    if (closing) return;
    setClosing(true);
    setTimeout(() => router.push("/review"), CLOSE_MS);
  }

  /**
   * Dismissal, guarded.
   *
   * Escape, the backdrop and the back button all landed here and closed
   * immediately, and the form went with the drawer — verified on draft 57:
   * typing enabled **Save changes**, Escape closed with no prompt, and
   * reopening showed the caption back at its original 747 characters. Approve,
   * Reject and the inset upload had each been given an explicit
   * `if (dirty) await updateDraft(...)` for exactly this reason; plain
   * dismissal was the path nobody had covered.
   *
   * It asks rather than saving, and that is the whole of the answer to the
   * client's "auto save when edit the text directly?" (G4, 2026-08-16). Saving
   * on close would commit a Gemini rewrite that the operator closed the drawer
   * to get away from, which is precisely what their own round-2 A2 asked us to
   * prevent: **rewrite proposes, Save writes, Revert undoes.** Nothing is
   * written that nobody asked to write, and nothing is thrown away in silence.
   *
   * Only when there is something to lose, so the ordinary close is untouched.
   */
  function requestClose() {
    if (dirty.current) setConfirming(true);
    else close();
  }

  return (
    <>
      <Drawer
        open={!closing}
        onOpenChange={(next) => {
          if (!next) requestClose();
        }}
      >
        <DrawerContent>
          <DrawerTitle>Draft {draftId}</DrawerTitle>
          <DrawerDescription>Review and edit draft {draftId}.</DrawerDescription>
          {/* The drawer scrolls, not the page behind it. */}
          <div className="min-h-0 flex-1 overflow-y-auto px-7 py-6">
            {/* `close`, not `requestClose`: a decision already saved the form
                on its way out, so asking would be asking about nothing. */}
            <DraftDetail draftId={draftId} onDecided={close} dirtyRef={dirty} />
          </div>
        </DrawerContent>
      </Drawer>

      <Dialog open={confirming} onOpenChange={setConfirming}>
        <DialogContent className="sm:max-w-md" aria-describedby={undefined}>
          <DialogTitle>Discard unsaved changes?</DialogTitle>
          <p className="text-sm text-muted-foreground">
            Your edits to draft {draftId} have not been saved.
          </p>
          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => setConfirming(false)}>
              Keep editing
            </Button>
            <Button
              variant="destructive"
              onClick={() => {
                setConfirming(false);
                close();
              }}
            >
              Discard
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
