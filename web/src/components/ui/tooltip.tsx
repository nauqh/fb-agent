"use client";

import * as React from "react";
import { Tooltip as TooltipPrimitive } from "radix-ui";

import { cn } from "@/lib/utils";

/**
 * A label for a control that has lost its own.
 *
 * Solid `bg-foreground` on `text-background` rather than a bordered panel: the
 * collapsed rail's only job here is to name an icon, and an inverted chip reads
 * at a glance where a pale outlined box does not. `delayDuration={0}` for the
 * same reason - the browser's native `title` takes about a second to appear,
 * which is long enough to have already clicked the wrong icon.
 */

function TooltipProvider({
  delayDuration = 0,
  ...props
}: React.ComponentProps<typeof TooltipPrimitive.Provider>) {
  return <TooltipPrimitive.Provider delayDuration={delayDuration} {...props} />;
}

function Tooltip(props: React.ComponentProps<typeof TooltipPrimitive.Root>) {
  return <TooltipPrimitive.Root data-slot="tooltip" {...props} />;
}

/**
 * Radix opens the tooltip on *any* focus, and that is what made the rail's
 * chips appear on their own.
 *
 * Clicking a collapsed rail icon leaves DOM focus on it - it is a link or a
 * button, and nothing takes focus away afterwards. So every later focus
 * *restore* fired `focus` again with the pointer parked somewhere else
 * entirely: coming back to the tab, alt-tab, a dialog closing. Radix's own
 * guard only covers the click itself (a `pointerdown` ref cleared on
 * `pointerup`), not the focus the click left behind.
 *
 * `:focus-visible` is the distinction the browser already draws: it is false
 * for focus a pointer put there and true for focus arrived at by keyboard, and
 * it survives a tab switch. `preventDefault()` is how Radix's
 * `composeEventHandlers` is asked to skip its own handler, so tabbing to a
 * collapsed icon still names it.
 */
function TooltipTrigger({
  onFocus,
  ...props
}: React.ComponentProps<typeof TooltipPrimitive.Trigger>) {
  return (
    <TooltipPrimitive.Trigger
      data-slot="tooltip-trigger"
      onFocus={(event) => {
        onFocus?.(event);
        if (!event.currentTarget.matches(":focus-visible")) event.preventDefault();
      }}
      {...props}
    />
  );
}

function TooltipContent({
  className,
  sideOffset = 6,
  children,
  ...props
}: React.ComponentProps<typeof TooltipPrimitive.Content>) {
  return (
    <TooltipPrimitive.Portal>
      <TooltipPrimitive.Content
        data-slot="tooltip-content"
        sideOffset={sideOffset}
        className={cn(
          "z-50 w-fit max-w-xs origin-(--radix-tooltip-content-transform-origin) rounded-lg",
          "bg-foreground px-3 py-1.5 text-xs font-medium text-background shadow-lg",
          "data-[side=bottom]:slide-in-from-top-1 data-[side=left]:slide-in-from-right-1",
          "data-[side=right]:slide-in-from-left-1 data-[side=top]:slide-in-from-bottom-1",
          "data-open:animate-in data-open:fade-in-0 data-open:zoom-in-95",
          "data-closed:animate-out data-closed:fade-out-0 data-closed:zoom-out-95",
          className,
        )}
        {...props}
      >
        {children}
        {/* Radix's own triangle, not the usual rotated-square trick - that one
            carries a `-translate-y` tuned for a tooltip sitting above its
            trigger, and the rail's tooltips sit to the right of theirs. */}
        <TooltipPrimitive.Arrow className="fill-foreground" width={11} height={5} />
      </TooltipPrimitive.Content>
    </TooltipPrimitive.Portal>
  );
}

export { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger };
