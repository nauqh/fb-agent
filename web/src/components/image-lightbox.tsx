"use client";

import { useState } from "react";
import { Eye } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog";

/**
 * View the composite full size, without opening the draft.
 *
 * Ported from the old app's `ImageViewFullButton`, which sat on the row
 * thumbnail for the same reason it does here: at 88px you can tell a picture
 * exists and roughly what it is of, and nothing about whether the panel wrapped
 * badly or the watermark landed on someone's face. Those are the things a
 * reviewer is actually looking for, and they should not cost a round trip
 * through the editor.
 *
 * Built on the shared Dialog rather than a hand-rolled overlay, so Escape, the
 * focus trap and the scroll lock come with it.
 */
export function ViewFullButton({ src, alt }: { src: string; alt: string }) {
  const [open, setOpen] = useState(false);

  return (
    <>
      <Button
        type="button"
        variant="secondary"
        size="icon-sm"
        aria-label="View full image"
        className="absolute right-1 bottom-1 z-10 bg-background/85 opacity-0 shadow-sm backdrop-blur-sm transition-opacity group-hover/thumb:opacity-100 focus-visible:opacity-100"
        onClick={(event) => {
          // The row opens the draft; this must not.
          event.stopPropagation();
          event.preventDefault();
          setOpen(true);
        }}
      >
        <Eye className="size-3.5" />
      </Button>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent
          showCloseButton={false}
          className="w-auto max-w-[min(96vw,1100px)] border-0 bg-transparent p-0 ring-0"
          onClick={(event) => event.stopPropagation()}
        >
          <DialogTitle className="sr-only">{alt}</DialogTitle>
          <DialogDescription className="sr-only">
            The composed image at full size.
          </DialogDescription>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={src}
            alt={alt}
            className="max-h-[94vh] w-auto rounded-2xl shadow-2xl"
          />
        </DialogContent>
      </Dialog>
    </>
  );
}
