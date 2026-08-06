"use client";

import * as React from "react";
import { Dialog as DialogPrimitive } from "radix-ui";
import { XIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/**
 * A panel that slides in from the right and covers most of the screen height.
 *
 * The same Radix dialog `ui/dialog.tsx` uses — focus trapping, Escape and
 * scroll locking come with it — anchored to the right edge rather than centred.
 *
 * Inset top and bottom to 90vh instead of running edge to edge, so the queue
 * stays visible above and below it and the drawer reads as sitting *over* the
 * screen rather than replacing it. Not full width for the same reason.
 */

function Drawer(props: React.ComponentProps<typeof DialogPrimitive.Root>) {
  return <DialogPrimitive.Root data-slot="drawer" {...props} />;
}

function DrawerContent({
  className,
  children,
  ...props
}: React.ComponentProps<typeof DialogPrimitive.Content>) {
  return (
    <DialogPrimitive.Portal>
      <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-black/40 duration-200 data-open:animate-in data-open:fade-in-0 data-closed:animate-out data-closed:fade-out-0" />
      <DialogPrimitive.Content
        data-slot="drawer-content"
        className={cn(
          "fixed top-[5vh] right-0 z-50 flex h-[90vh] w-[92vw] max-w-[1120px] flex-col",
          "rounded-l-2xl border bg-background shadow-2xl duration-300 outline-none",
          "data-open:animate-in data-open:slide-in-from-right data-closed:animate-out data-closed:slide-out-to-right",
          className,
        )}
        {...props}
      >

        <DialogPrimitive.Close asChild>
          <Button variant="ghost" size="icon-sm" className="absolute top-3 right-4 z-10">
            <XIcon />
            <span className="sr-only">Close</span>
          </Button>
        </DialogPrimitive.Close>

        {children}
      </DialogPrimitive.Content>
    </DialogPrimitive.Portal>
  );
}

/** Radix warns without these; the panel supplies its own visible header. */
function DrawerTitle({ className, ...props }: React.ComponentProps<typeof DialogPrimitive.Title>) {
  return <DialogPrimitive.Title className={cn("sr-only", className)} {...props} />;
}

function DrawerDescription({
  className,
  ...props
}: React.ComponentProps<typeof DialogPrimitive.Description>) {
  return <DialogPrimitive.Description className={cn("sr-only", className)} {...props} />;
}

export { Drawer, DrawerContent, DrawerTitle, DrawerDescription };
