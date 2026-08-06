"use client";

import * as React from "react";
import { Dialog as DialogPrimitive } from "radix-ui";
import { XIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/**
 * A panel that rises from the bottom and covers most of the screen.
 *
 * The same Radix dialog `ui/dialog.tsx` uses — focus trapping, Escape and
 * scroll locking come with it — anchored to the bottom edge instead of centred.
 * It replaced a right-hand sheet: at 1,180px wide that still left the draft in
 * a column, and the composite is portrait, so height is the dimension this
 * screen is actually short of.
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
          "fixed inset-x-0 bottom-0 z-50 flex h-[90vh] flex-col rounded-t-2xl border-t bg-background shadow-2xl duration-300 outline-none",
          "data-open:animate-in data-open:slide-in-from-bottom data-closed:animate-out data-closed:slide-out-to-bottom",
          className,
        )}
        {...props}
      >
        {/* The grab handle says "this came from the bottom and goes back
            there". Decorative — dragging is not wired up. */}
        <div className="mx-auto mt-2.5 h-1 w-10 shrink-0 rounded-full bg-border" />

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
