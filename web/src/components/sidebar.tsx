"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  CalendarDays,
  Globe,
  Inbox,
  Layers,
  PanelLeft,
  PenLine,
  Settings2,
  type LucideIcon,
} from "lucide-react";

import { Logo } from "@/components/logo";
import { SignOut } from "@/components/sign-out";
import { ThemeToggle } from "@/components/theme-toggle";
import { listDrafts } from "@/lib/api/drafts";
import { useCart } from "@/lib/cart";
import { usePageScope } from "@/lib/page-scope";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { COLLAPSE_COOKIE } from "@/lib/sidebar-cookie";
import { useQuery } from "@/lib/use-query";
import { cn } from "@/lib/utils";

/**
 * The shell's navigation: a rail on `lg`, a bar above the screen below it.
 *
 * Settings is deliberately not in the same group as the other three. Sources →
 * Review → Schedule is the operator loop, walked several times a day; Settings
 * is a read-only window onto what the run is configured with, opened rarely.
 * Grouping them together would suggest four equal destinations. It sits at the
 * bottom on `lg` (`mt-auto`) but stays in the same list, so the mobile bar can
 * lay all four out in a row without a second copy of the markup.
 *
 * Collapsing is `lg`-only, and it is driven entirely by `lg:` classes rather
 * than by branching in JS — below `lg` the rail is already a horizontal bar
 * with nothing to reclaim, and a JS branch would strip the brand off the phone
 * layout too.
 */

const LINKS: { href: string; label: string; icon: LucideIcon }[] = [
  { href: "/sources", label: "Sources", icon: Layers },
  // Beside Sources rather than after Review: both are ways of starting a run,
  // and the loop below them — Review, Schedule — is the same whichever one fed
  // it. The topic field used to live in the Sources dock and moved here.
  { href: "/manual", label: "Manual", icon: PenLine },
  { href: "/review", label: "Review", icon: Inbox },
  { href: "/schedule", label: "Schedule", icon: CalendarDays },
];

/**
 * The two configuration screens, kept apart because they answer different
 * questions. Settings is "this Page" — its feeds, its watermark, which
 * competitors it reads. Global is "the account" — the competitor pool and its
 * Metricool budget, the image layout, the prompts. Neither is scoped by the
 * Page switcher in the same way, and mixing them put an account-wide number
 * under a per-Page heading.
 */
const CONFIG: { href: string; label: string; icon: LucideIcon }[] = [
  { href: "/settings", label: "Settings", icon: Settings2 },
  { href: "/global", label: "Global", icon: Globe },
];

/** The old app's rail: a plain ghost square, tinted only on hover. */
const GHOST_ICON =
  "flex size-8 shrink-0 items-center justify-center rounded-md text-sidebar-foreground transition-colors hover:bg-sidebar-accent hover:text-sidebar-accent-foreground focus-visible:ring-2 focus-visible:ring-sidebar-ring focus-visible:outline-none";

export function Sidebar({
  // Collapsed unless the layout's cookie says otherwise — matching the default
  // there, so a Sidebar rendered without the prop cannot disagree with the
  // server about how wide the first paint should be.
  defaultCollapsed = true,
}: {
  defaultCollapsed?: boolean;
}) {
  const pathname = usePathname();
  const cart = useCart();

  /**
   * Seeded from a cookie the server already read, rather than from
   * localStorage in an effect. localStorage is not readable during the server
   * render, so the rail would mount expanded and snap shut on every page load;
   * the cookie arrives with the request, so the first paint is already right.
   */
  const [collapsed, setCollapsed] = useState(defaultCollapsed);

  function toggle() {
    const next = !collapsed;
    setCollapsed(next);
    // A year, path-wide. No `secure` — this is served over http on the laptop.
    document.cookie = `${COLLAPSE_COOKIE}=${next ? "1" : "0"}; path=/; max-age=31536000; samesite=lax`;
  }

  // Drafts still needing a decision, and rows currently in flight — the two
  // numbers that tell the operator there is work waiting without opening the
  // screen.
  // Scoped to the selected Page, like the queue itself. A badge reading 3 over
  // a Review screen showing 0 is the kind of wrong that gets ignored rather
  // than reported.
  const { pageId } = usePageScope();
  const { data: queue } = useQuery(
    async () => {
      const [review, generating] = await Promise.all([
        listDrafts({ status: "review", page_id: pageId! }),
        listDrafts({ status: "generating", page_id: pageId! }),
      ]);
      return { review: review.length, generating: generating.length };
    },
    [pageId],
    {
      enabled: pageId !== null,
      intervalMs: 4_000,
      pollWhile: (counts) => counts === null || counts.generating > 0,
    },
  );

  // The Cart is in-memory and lives only on Sources, so without a count here a
  // Cart filled and then navigated away from is invisible.
  const counts: Record<string, number | null> = {
    "/sources": cart.count || null,
    "/review": queue?.review || null,
  };

  const toggleLabel = collapsed ? "Expand sidebar" : "Collapse sidebar";

  return (
    <TooltipProvider>
      <aside
        className={cn(
          "z-40 flex shrink-0 flex-col border-b bg-sidebar text-sidebar-foreground",
          "lg:h-screen lg:border-r lg:border-b-0",
          /**
           * Width is the only thing that moves, and the icons do not move at all.
           *
           * `px-3` on the nav and `px-3` on each item put every icon at x=24–40
           * in both states, so 64px collapsed is not an arbitrary width: it is
           * 24 + 16 + 24, the number that leaves the icons exactly where the
           * 240px rail already had them. Centring them with `justify-center`
           * instead makes them jump to the middle the instant the label hides,
           * racing ahead of the width animation — which was the jank.
           *
           * `overflow-hidden` so the labels clip as the rail narrows rather than
           * wrapping onto a second line on the way. `ease-linear` matches the
           * old app's rail. 300ms rather than the old app's 200: at this width
           * the shorter one arrives before the eye has followed it.
           */
          "transition-[width] duration-300 ease-linear lg:overflow-hidden",
          collapsed ? "lg:w-16" : "lg:w-60",
        )}
      >
        {/* `lg:pb-3`, not `pb-1`: the Page heading used to sit under this row
            and supply the gap down to the first icon. With it gone the header
            owns that spacing itself — and the same value in both states, so
            collapsing no longer shifts the nav vertically. */}
        {/* No `gap` here: the only gap that matters is the one between the
            brand and the trigger, and it has to shrink *with* the brand or it
            keeps 10px of the 32px collapsed content box and pushes the trigger
            off the edge. It rides on the brand as `mr` instead. */}
        <div className="flex h-14 shrink-0 items-center px-4 whitespace-nowrap lg:h-auto lg:pt-5 lg:pb-3">
          {/**
           * Collapsed, the rail carries no brand — the trigger is the only
           * thing in the header, as the old app's is.
           *
           * It gets there by shrinking, not by `hidden`. `hidden` is instant,
           * so the brand vanished on the click while the rail still had 300ms
           * of travel left — the one part of the collapse that was not
           * animating. `width: auto` cannot be transitioned, so `max-width`
           * does the work: 10rem is clear of its ~90px natural width, so it
           * never clips while open.
           */}
          <Link
            href="/sources"
            className={cn(
              "flex items-center gap-2.5 text-sm font-semibold tracking-tight",
              "lg:overflow-hidden lg:transition-[max-width,opacity,margin] lg:duration-300 lg:ease-linear",
              collapsed
                ? "lg:mr-0 lg:max-w-0 lg:opacity-0"
                : "lg:mr-2.5 lg:max-w-40",
            )}
          >
            <Logo className="size-5 shrink-0" />
            fb<span className="text-muted-foreground">-agent</span>
          </Link>

          <div className="ml-auto lg:hidden">
            <Generating count={queue?.generating} />
          </div>

          {/* No tooltip on the trigger. The rail's width already says which
              way it goes, and a chip naming the control you are looking at is
              the kind of hint that only gets in the way. `aria-label` still
              carries the name for anything not looking at it. */}
          <button
            type="button"
            onClick={toggle}
            aria-label={toggleLabel}
            className={cn(
              GHOST_ICON,
              // After GHOST_ICON, not before: that string starts with
              // `flex`, and tailwind-merge resolves display conflicts
              // last-wins — ordered the other way the toggle reappears in
              // the mobile bar, where there is nothing to collapse.
              "hidden lg:flex",
              // Always `ml-auto`, never a switch to `mx-auto`. Once the brand
              // shrinks to nothing the collapsed content box is 64 − 32 = 32px
              // and the button is 32px, so "flush right" *is* centred — and it
              // glides there with the rail instead of jumping on the click.
              "lg:ml-auto",
            )}
          >
            {/* One icon, not a swapped pair: the rail's own width already says
              which way it will go, and a glyph that changes under the cursor
              is the more distracting of the two. */}
            <PanelLeft className="size-4" />
          </button>
        </div>

        <nav
          className={cn(
            // `px-3` is constant on purpose — see the width note above.
            "flex gap-1 overflow-x-auto px-3 py-2",
            // `lg:overflow-x-hidden` matters: `overflow-x-auto` above is for
            // the mobile bar, and left un-reset it makes the collapsed rail
            // scroll sideways — the labels stay in flow while faded, so they
            // overflow the 40px content box and this element, being its own
            // scroll container, offers to scroll to them. The aside's
            // `overflow-hidden` clips the paint but cannot stop that.
            "lg:min-h-0 lg:flex-1 lg:flex-col lg:gap-0.5 lg:overflow-x-hidden lg:overflow-y-auto lg:pt-1 lg:pb-3",
          )}
        >
          {LINKS.map((link) => (
            <Item
              key={link.href}
              {...link}
              active={pathname.startsWith(link.href)}
              count={counts[link.href]}
              collapsed={collapsed}
            />
          ))}

          <div className="lg:mt-auto lg:border-t lg:pt-2">
            {/* Only mounted when there is something in flight, so the footer
                does not reserve an empty strip above Settings — and hidden
                outright when collapsed rather than faded, because a 64px rail
                has no room to say "2 generating" and a faded block would sit
                there as a gap. */}
            {queue?.generating ? (
              <div
                className={cn(
                  "hidden px-3 py-2 lg:block",
                  collapsed && "lg:hidden",
                )}
              >
                <Generating count={queue.generating} />
              </div>
            ) : null}
            {CONFIG.map((link) => (
              <Item
                key={link.href}
                {...link}
                active={pathname.startsWith(link.href)}
                count={null}
                collapsed={collapsed}
              />
            ))}
            {/* Last, and below the two config screens rather than among them.
                Those are destinations with a URL and an active state; this is a
                control that changes nothing about where you are. It shares
                their row shape only so the icons stay in the same column. */}
            <ThemeToggle collapsed={collapsed} />
            <SignOut collapsed={collapsed} />
          </div>
        </nav>
      </aside>
    </TooltipProvider>
  );
}

function Item({
  href,
  label,
  icon: Icon,
  active,
  count,
  collapsed,
}: {
  href: string;
  label: string;
  icon: LucideIcon;
  active: boolean;
  count: number | null;
  collapsed: boolean;
}) {
  const link = (
    <Link
      href={href}
      aria-current={active ? "page" : undefined}
      className={cn(
        // `px-3` constant, and no `justify-center` — the icon must not move.
        "relative flex shrink-0 items-center gap-2.5 rounded-md px-3 py-2 text-sm whitespace-nowrap transition-colors",
        // Each row clips its own faded label, so the overflow never reaches
        // the nav. Hiding it only on the nav leaves the nav's scrollWidth
        // wider than its box, and a `hidden` scroll container still scrolls
        // when something inside it takes focus — which would slide the icons
        // out of line on a tab press.
        collapsed && "lg:overflow-hidden",
        // Full-contrast in both states. Greying the inactive items made the
        // icons look soft and out of focus rather than merely secondary; the
        // active one is already carried by its fill, its weight and the gold
        // rail, so it does not need the others dimmed to stand out.
        active
          ? "bg-sidebar-accent font-medium text-sidebar-accent-foreground"
          : "text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
      )}
    >
      {/* The active marker is the brand gold rather than another grey: it is
          the one accent the rest of the shell already uses, and it survives the
          low contrast between `--sidebar` and `--sidebar-accent`. */}
      {active ? (
        <span
          className="absolute inset-y-1.5 left-0 w-0.5 rounded-full bg-gold"
          aria-hidden
        />
      ) : null}

      <span className="relative shrink-0">
        <Icon className="size-4" />
        {/* Collapsed, the count has nowhere to sit, but "there is work waiting"
            is the one thing the rail must still say. */}
        {count && collapsed ? (
          <span className="absolute -top-0.5 -right-0.5 hidden size-1.5 rounded-full bg-gold lg:block" />
        ) : null}
      </span>

      {/**
       * Faded out, not `hidden`.
       *
       * `hidden` is instant, so on collapse every label vanished on the click
       * and the rail then spent 300ms shrinking around empty space — which is
       * what read as unsmooth. Keeping them in flow and fading them means the
       * text is still there, being clipped by the rail's `overflow-hidden` as
       * it narrows. They keep their width while faded, so the row overflows
       * its 40px box in the collapsed rail; that is exactly what gets clipped,
       * and nothing below `lg` is affected because the fade is `lg:` only.
       */}
      <span
        className={cn(
          "truncate transition-opacity duration-300 ease-linear",
          collapsed && "lg:opacity-0",
        )}
      >
        {label}
      </span>

      {count ? (
        <span
          className={cn(
            "ml-auto pl-2 text-xs tabular-nums text-muted-foreground",
            "transition-opacity duration-300 ease-linear",
            collapsed && "lg:opacity-0",
          )}
        >
          {count}
        </span>
      ) : null}
    </Link>
  );

  // Expanded, the label is already on screen and a tooltip repeating it is
  // noise. Collapsed, it is the only thing naming the icon.
  if (!collapsed) return link;

  return (
    <Tooltip>
      <TooltipTrigger asChild>{link}</TooltipTrigger>
      <TooltipContent side="right">{label}</TooltipContent>
    </Tooltip>
  );
}

function Generating({ count }: { count: number | undefined }) {
  if (!count) return null;

  return (
    <span className="inline-flex items-center gap-1.5 text-xs whitespace-nowrap text-muted-foreground">
      <span className="size-1.5 animate-pulse rounded-full bg-gold" />
      {count} generating
    </span>
  );
}
