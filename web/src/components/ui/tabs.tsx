"use client"

import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { Tabs as TabsPrimitive } from "radix-ui"

import { cn } from "@/lib/utils"

function Tabs({
  className,
  orientation = "horizontal",
  ...props
}: React.ComponentProps<typeof TabsPrimitive.Root>) {
  return (
    <TabsPrimitive.Root
      data-slot="tabs"
      data-orientation={orientation}
      className={cn(
        "group/tabs flex gap-2 data-horizontal:flex-col",
        className
      )}
      {...props}
    />
  )
}

// One pill shell, everywhere a screen switches between alternatives: Sources'
// Competitors/Tweets/RSS, Overview's Performance/Saved, Manual's two starting
// points, the Review drawer's Edit/Preview. Rounded-lg to match the app's
// buttons and chips — the pill's `rounded-full` read as a different element
// next to them. The active trigger is a solid pill rather than a white card
// with a shadow — the same shell Settings' Prompts tabs use, built by hand
// there because this component predates it. A second implementation of the
// same look is worse than widening this one, so the bespoke version was
// retired in favour of this.
//
// **The container is back, and it has no padding.** The tray bounds the group;
// the selected trigger fills its cell edge to edge and corner to corner, so the
// pill is a segment of the control rather than a chip floating inside it. That
// is the whole reason `p-0` and `gap-0` are not negotiable here: any padding or
// gap is tray showing through around the thing that is meant to fill it.
const tabsListVariants = cva(
  "group/tabs-list inline-flex w-fit items-center justify-center gap-0 rounded-lg border bg-muted/40 p-0 text-muted-foreground group-data-horizontal/tabs:h-auto group-data-vertical/tabs:h-fit group-data-vertical/tabs:flex-col data-[variant=line]:rounded-none",
  {
    variants: {
      variant: {
        default: "",
        line: "gap-1 rounded-none border-none bg-transparent p-0",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
)

type PillRect = {
  x: number
  y: number
  width: number
  height: number
  radius: string
}

const same = (a: PillRect | null, b: PillRect | null) =>
  a === b ||
  (!!a &&
    !!b &&
    a.x === b.x &&
    a.y === b.y &&
    a.width === b.width &&
    a.height === b.height &&
    a.radius === b.radius)

// The pill's own corners, rather than clipping it with `overflow-hidden` on the
// list. **The obvious way does not work.** A rounded clip is not something the
// compositor supports, so a transformed child escapes it or renders jagged
// corners precisely while it animates — WebKit #98538 and the Chromium
// graphics-dev thread on the same. The advice is either `contain: paint` or
// giving the child matching radii; the second needs no clip at all, and it also
// leaves the focus ring unclipped, which `overflow-hidden` would have eaten.
//
// Only the ends are round, and only on the outside: the pill at the left of a
// horizontal bar is round on the left and square where it meets its neighbour.
// The radius is read off the list rather than hardcoded, minus its border,
// which is the geometry of one box nested inside another — a caller that
// changes `rounded-lg` gets a pill that still fits.
function pillRadius(list: HTMLElement, first: boolean, last: boolean) {
  const style = getComputedStyle(list)
  const inner = Math.max(
    0,
    parseFloat(style.borderTopLeftRadius) - parseFloat(style.borderTopWidth)
  )
  const [start, end] = [first ? inner : 0, last ? inner : 0]
  return style.flexDirection === "column"
    ? `${start}px ${start}px ${end}px ${end}px`
    : `${start}px ${end}px ${end}px ${start}px`
}

// The active pill slides between triggers instead of blinking out of one and
// into the next. One element measured against the active trigger, moved with a
// transform — the pill is a single continuous object, which is the whole effect.
//
// **The CSS pill on the trigger stays and is the fallback.** Until the first
// measurement lands there is no `data-indicator` on the list, so the trigger
// paints its own `bg-foreground` exactly as before: server-rendered HTML, the
// frame before hydration, and JS-disabled all show a correct static pill. The
// swap happens in one commit — the indicator appears at the same rect as the
// background it replaces — so there is no flash between the two.
function TabsList({
  className,
  variant = "default",
  children,
  ...props
}: React.ComponentProps<typeof TabsPrimitive.List> &
  VariantProps<typeof tabsListVariants>) {
  const listRef = React.useRef<HTMLDivElement>(null)
  const [pill, setPill] = React.useState<PillRect | null>(null)

  const measure = React.useCallback(() => {
    const list = listRef.current
    if (!list) return
    // The whole row, not just the active one: which end it sits at decides
    // which of its corners are round. `:first-child` cannot answer that — the
    // indicator itself is the list's first child.
    const triggers = [
      ...list.querySelectorAll<HTMLElement>('[data-slot="tabs-trigger"]'),
    ]
    const index = triggers.findIndex((t) => t.dataset.state === "active")
    // No active trigger is a real state — a Tabs whose value matches nothing —
    // and the indicator has to leave rather than sit on the last place it saw.
    if (index === -1) return setPill(null)
    const active = triggers[index]
    const box = list.getBoundingClientRect()
    const target = active.getBoundingClientRect()
    // The list's border, subtracted. `absolute` is resolved against the padding
    // box and `getBoundingClientRect` is the border box, so without this the
    // pill sits one border-width down and to the right of the trigger it is
    // meant to cover — visible as a hairline of pill along two edges.
    const edge = getComputedStyle(list)
    const next = {
      x: target.left - box.left - parseFloat(edge.borderLeftWidth),
      y: target.top - box.top - parseFloat(edge.borderTopWidth),
      width: target.width,
      height: target.height,
      radius: pillRadius(list, index === 0, index === triggers.length - 1),
    }
    setPill((current) => (same(current, next) ? current : next))
  }, [])

  React.useEffect(() => {
    const list = listRef.current
    if (!list) return
    measure()

    // Three things move the pill and only one of them is a click. A trigger can
    // change width without the list resizing (a count in the label going from
    // 9 to 10), and the list can resize without any trigger changing.
    const resize = new ResizeObserver(measure)
    resize.observe(list)
    for (const trigger of list.querySelectorAll('[data-slot="tabs-trigger"]')) {
      resize.observe(trigger)
    }
    const state = new MutationObserver(measure)
    state.observe(list, {
      subtree: true,
      attributes: true,
      // Narrowed on purpose: this component writes `data-indicator` on the
      // list, and observing every attribute would make that write re-enter here.
      attributeFilter: ["data-state"],
    })
    return () => {
      resize.disconnect()
      state.disconnect()
    }
  }, [measure, children])

  const sliding = variant === "default" && pill !== null

  return (
    <TabsPrimitive.List
      ref={listRef}
      data-slot="tabs-list"
      data-variant={variant}
      data-indicator={sliding ? "on" : undefined}
      className={cn(tabsListVariants({ variant }), "relative", className)}
      {...props}
    >
      {sliding ? (
        <span
          aria-hidden
          data-slot="tabs-indicator"
          className="absolute top-0 left-0 z-0 bg-foreground transition-[translate,width,height,border-radius] duration-200 ease-out motion-reduce:transition-none"
          style={{
            translate: `${pill.x}px ${pill.y}px`,
            width: pill.width,
            height: pill.height,
            borderRadius: pill.radius,
          }}
        />
      ) : null}
      {children}
    </TabsPrimitive.List>
  )
}

function TabsTrigger({
  className,
  ...props
}: React.ComponentProps<typeof TabsPrimitive.Trigger>) {
  return (
    <TabsPrimitive.Trigger
      data-slot="tabs-trigger"
      className={cn(
        // `text-xs` rather than shadcn's stock `text-sm`: every other small
        // control in this app — buttons, chips, meta counts — is 12px, and at
        // 14px plus the wider pill padding this read oversized next to them.
        // Square, except at the ends of the bar, where the fill has to follow
        // the tray's corners. `first:`/`last:` read as the first and last child
        // of the list, which is only correct while the indicator is absent —
        // and that is exactly when these matter, because the indicator brings
        // its own computed corners and blanks this fill out.
        //
        // Off the same token as the tray, less its border, which is what
        // `pillRadius` computes at runtime. Hardcoding it was wrong within the
        // hour: `--radius` is 4px here, not the 8px `rounded-lg` looks like.
        "relative z-10 inline-flex flex-1 items-center justify-center gap-1.5 rounded-none first:rounded-l-[calc(var(--radius-lg)-1px)] last:rounded-r-[calc(var(--radius-lg)-1px)] px-2.5 py-1 text-xs font-medium whitespace-nowrap text-muted-foreground transition-colors group-data-vertical/tabs:w-full group-data-vertical/tabs:justify-start hover:text-foreground focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-1 focus-visible:outline-ring disabled:pointer-events-none disabled:opacity-50 has-data-[icon=inline-end]:pr-1 has-data-[icon=inline-start]:pl-1 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-3.5",
        "group-data-[variant=default]/tabs-list:data-active:bg-foreground group-data-[variant=default]/tabs-list:data-active:text-background",
        // Handed over to the sliding indicator once it has measured itself.
        // Important, and it has to be: this and the `bg-foreground` above are
        // both one variant deep on the same property, so which of them wins is
        // decided by Tailwind's ordering rather than by anything written here.
        // It lost — and a trigger that keeps its own pill paints the
        // destination solid the instant it is clicked, while the indicator is
        // still travelling towards it. Three pills on screen at once.
        "group-data-[indicator=on]/tabs-list:data-active:bg-transparent!",
        // The label inverts to `text-background`, so it is only legible once
        // the pill is under it. Measured: without the delay the text is 91%
        // white while the pill has covered barely half the trigger — white on
        // a white bar, for about three frames. Scoped to `data-active` so it
        // delays the arriving label and nothing else: hover stays instant, and
        // the leaving label drops to muted while the pill is still on it,
        // which is dark-on-dark for a moment but never invisible.
        "group-data-[indicator=on]/tabs-list:data-active:delay-100",
        "after:absolute after:bg-foreground after:opacity-0 after:transition-opacity group-data-horizontal/tabs:after:inset-x-0 group-data-horizontal/tabs:after:bottom-[-5px] group-data-horizontal/tabs:after:h-0.5 group-data-vertical/tabs:after:inset-y-0 group-data-vertical/tabs:after:-right-1 group-data-vertical/tabs:after:w-0.5 group-data-[variant=line]/tabs-list:data-active:text-foreground group-data-[variant=line]/tabs-list:data-active:after:opacity-100",
        className
      )}
      {...props}
    />
  )
}

function TabsContent({
  className,
  ...props
}: React.ComponentProps<typeof TabsPrimitive.Content>) {
  return (
    <TabsPrimitive.Content
      data-slot="tabs-content"
      className={cn("flex-1 text-sm outline-none", className)}
      {...props}
    />
  )
}

export { Tabs, TabsList, TabsTrigger, TabsContent, tabsListVariants }
