"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  BarChart3,
  CalendarDays,
  Check,
  ChevronDown,
  Clapperboard,
  Globe,
  History,
  Inbox,
  Layers,
  PanelLeft,
  PenLine,
  Rocket,
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
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { COLLAPSE_COOKIE } from "@/lib/sidebar-cookie";
import { useQuery } from "@/lib/use-query";
import { cn } from "@/lib/utils";

/**
 * The shell's navigation: a panel on `lg`, a bar above the screen below it.
 *
 * Settings is deliberately not in the same group as the other three. Sources →
 * Review → Schedule is the operator loop, walked several times a day; Settings
 * is a read-only window onto what the run is configured with, opened rarely.
 * Grouping them together would suggest four equal destinations. It sits at the
 * bottom on `lg` (`mt-auto`) but stays in the same list, so the mobile bar can
 * lay all four out in a row without a second copy of the markup.
 *
 * ## Collapsing
 *
 * Collapsed does **not** mean a narrower rail. The panel only ever renders in
 * one form - full width, labelled - and collapsing slides that one panel off
 * the left edge, leaving a 56px gutter holding a single toggle. Hovering the
 * gutter brings the panel back as a floating card over the screen, and the
 * screen does not move while it is there.
 *
 * The icon-rail collapse this replaced kept a 64px strip of icons on screen and
 * paid for it everywhere: labels that had to fade rather than hide, counts that
 * became meaningless gold dots, tooltips to name icons that had lost their
 * text, a second copy of the workspace switcher drawn as one glyph, and a
 * constant `px-3` that every row in three files had to honour so nothing jumped
 * as the width animated. None of that survives here, because there is no second
 * geometry to keep in sync - there is one panel, and it is either in the flow
 * or floating over it.
 *
 * `lg`-only, in CSS rather than a JS branch: below `lg` the nav is already a
 * horizontal bar with nothing to reclaim, and a JS branch would take the brand
 * off the phone layout too.
 */

const LINKS: { href: string; label: string; icon: LucideIcon }[] = [
  // First: it is the only screen about what already went out, and the one an
  // operator opens to decide what to write next.
  { href: "/overview", label: "Overview", icon: BarChart3 },
  { href: "/sources", label: "Sources", icon: Layers },
  // Beside Sources rather than after Review: both are ways of starting a run,
  // and the loop below them - Review, Schedule - is the same whichever one fed
  // it. The topic field used to live in the Sources dock and moved here.
  { href: "/manual", label: "Manual", icon: PenLine },
  { href: "/review", label: "Review", icon: Inbox },
  { href: "/schedule", label: "Schedule", icon: CalendarDays },
];

/**
 * The two configuration screens, kept apart because they answer different
 * questions. Settings is "this Page" - its feeds, its watermark, which
 * competitors it reads. Global is "the account" - the competitor pool and its
 * Metricool budget, the image layout, the prompts. Neither is scoped by the
 * Page switcher in the same way, and mixing them put an account-wide number
 * under a per-Page heading.
 */
const CONFIG: { href: string; label: string; icon: LucideIcon }[] = [
  { href: "/settings", label: "Settings", icon: Settings2 },
  { href: "/global", label: "Global", icon: Globe },
];

/**
 * The Shorts workspace's whole navigation.
 *
 * Deliberately small: the v1 tool is produce → history → settings and nothing
 * else. The group renders in place of the Facebook `LINKS` when the workspace
 * switcher says Shorts - same panel, same active-state gold, same collapse
 * rules, different destinations. Publishing, metrics and the channel picker are
 * not here yet, and adding a route to this list is how they arrive.
 */
const SHORTS_LINKS: { href: string; label: string; icon: LucideIcon }[] = [
  { href: "/shorts", label: "Produce", icon: Clapperboard },
  { href: "/shorts/overview", label: "Overview", icon: BarChart3 },
  { href: "/shorts/history", label: "History", icon: History },
];

const SHORTS_CONFIG: { href: string; label: string; icon: LucideIcon }[] = [
  { href: "/shorts/settings", label: "Shorts Settings", icon: Rocket },
];

/** The two workspaces. Path-driven: `/shorts*` is Shorts, everything else is
 *  the Facebook agent. This is the whole "switch between everything" - one
 *  menu, and the nav group under it swaps. */
type Workspace = "facebook" | "shorts";

function workspaceOf(pathname: string): Workspace {
  return pathname.startsWith("/shorts") ? "shorts" : "facebook";
}

/**
 * The switcher's own list. Ordered as the menu reads, and the only place a
 * workspace's name and mark are written down.
 */
const WORKSPACES: {
  id: Workspace;
  label: string;
  mark: "facebook" | "youtube";
  home: string;
}[] = [
  { id: "facebook", label: "Facebook", mark: "facebook", home: "/sources" },
  { id: "shorts", label: "Shorts", mark: "youtube", home: "/shorts" },
];

/**
 * Which nav href owns the current path. The longest match wins.
 *
 * Neither simpler rule works on its own. A bare `startsWith` lit two rows at
 * once in the Shorts workspace - `/shorts` is a string prefix of
 * `/shorts/history`, so Produce stayed gold on every screen in the group.
 * Exact-match-only would fix that but unlights Review on `/review/[id]`, which
 * is a real screen.
 *
 * Longest-match settles both, because it asks which link is the *most
 * specific* one covering this path: on `/review/7` only `/review` matches; on
 * `/shorts/history` both `/shorts` and `/shorts/history` match and the longer
 * one takes it. The `/` in the prefix test keeps `/settings` from claiming a
 * hypothetical `/settings-v2`.
 *
 * Pass every href in the rail - the winner can live in the other group
 * (`/shorts` is in `SHORTS_LINKS`, `/shorts/settings` in `SHORTS_CONFIG`).
 */
function activeHref(pathname: string, hrefs: string[]): string | null {
  const matches = hrefs.filter(
    (href) => pathname === href || pathname.startsWith(`${href}/`),
  );
  if (matches.length === 0) return null;
  return matches.reduce((best, href) => (href.length > best.length ? href : best));
}

/**
 * The peek's hover zone, in viewport pixels.
 *
 * Deliberately coordinates rather than `onPointerEnter` on a strip element, and
 * the reason is the browser's own chrome. With a vertical-tabs sidebar or a
 * side panel open, the pointer leaves the *page* to the left many times an
 * hour - and `pointerleave` cannot tell that from "went back to work", so the
 * panel kept slamming shut the moment the cursor crossed into the browser's
 * furniture. A pointer that has left the window sends no `pointermove` at all,
 * so reading coordinates means the panel simply stays as it was.
 *
 * It also buys a target worth aiming at. The strip this replaced was the 12px
 * between the screen edge and the toggle, which asked for real care to hit.
 */

/** How far in from the left edge still counts as reaching for the panel. */
const PEEK_EDGE_X = 72;

/**
 * ...and how far down. Everything above this is the toggle button's: it sits
 * at y=26 and is 36px tall, so 72 clears it with room to spare.
 *
 * Without this the button is unusable. The panel paints above it, so a peek
 * triggered by *approaching* the toggle draws the panel straight over the
 * control being reached for and swallows the click. Excluding the whole band
 * rather than the button's own rect matters: coming in from the right at the
 * button's height would otherwise cross the live zone before arriving.
 */
const PEEK_EDGE_TOP = 72;

/** The floating panel's right edge: 8px inset + 256px of panel (`lg:w-64`).
 *  Past this the pointer is over the screen again, which is the one gesture
 *  that closes the peek - so this has to move whenever the width does. */
const PEEK_PANEL_RIGHT = 264;

/** The old app's rail: a plain ghost square, tinted only on hover. */
const GHOST_ICON =
  "flex size-8 shrink-0 items-center justify-center rounded-md text-sidebar-foreground transition-colors hover:bg-sidebar-accent hover:text-sidebar-accent-foreground focus-visible:ring-2 focus-visible:ring-sidebar-ring focus-visible:outline-none";

/** The Facebook mark - a workspace glyph drawn as the brand itself, not an
 *  invented icon. `currentColor` so the rail's tinting applies like any other
 *  icon. Simple-icons path. */
function FacebookMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" className={className} aria-hidden>
      <path d="M24 12.073c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.99 4.388 10.954 10.125 11.854v-8.385H7.078v-3.47h3.047V9.43c0-3.007 1.792-4.669 4.533-4.669 1.312 0 2.686.235 2.686.235v2.953H15.83c-1.491 0-1.956.925-1.956 1.874v2.25h3.328l-.532 3.47h-2.796v8.385C19.612 23.027 24 18.062 24 12.073z" />
    </svg>
  );
}

/** The YouTube mark - same role, opposite workspace. Simple-icons path. */
function YoutubeMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" className={className} aria-hidden>
      <path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z" />
    </svg>
  );
}

export function Sidebar({
  // Collapsed unless the layout's cookie says otherwise - matching the default
  // there, so a Sidebar rendered without the prop cannot disagree with the
  // server about how wide the first paint should be.
  defaultCollapsed = true,
}: {
  defaultCollapsed?: boolean;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const cart = useCart();

  // The workspace split, computed once: path-driven, so a refresh lands in the
  // same workspace and a link shared from the other one flips the whole nav.
  const workspace = workspaceOf(pathname);
  const links = workspace === "shorts" ? SHORTS_LINKS : LINKS;
  const config = workspace === "shorts" ? SHORTS_CONFIG : CONFIG;
  // Non-null: `workspaceOf` only ever returns an id that is in the list.
  const activeWorkspace = WORKSPACES.find((w) => w.id === workspace)!;

  // One winner across both groups, so exactly one row can be gold.
  const current = activeHref(pathname, [
    ...links.map((link) => link.href),
    ...config.map((link) => link.href),
  ]);

  /**
   * Open state of the workspace menu, kept here rather than left to Radix,
   * because the peek has to know about it.
   *
   * The menu is portalled to `<body>`, so it is not a descendant of the panel
   * and the pointer moving onto it is, as far as the peek is concerned, the
   * pointer going back to the screen. Without this the panel closes out from
   * under its own open menu.
   */
  const [menuOpen, setMenuOpen] = useState(false);

  /**
   * Seeded from a cookie the server already read, rather than from
   * localStorage in an effect. localStorage is not readable during the server
   * render, so the rail would mount expanded and snap shut on every page load;
   * the cookie arrives with the request, so the first paint is already right.
   */
  const [collapsed, setCollapsed] = useState(defaultCollapsed);

  /**
   * Whether the collapsed panel is currently floating over the screen.
   *
   * Lives on the wrapper, not on the gutter, because the panel is a *DOM* child
   * of the wrapper even though it paints outside it. `mouseleave` walks the
   * tree, not the box, so moving the pointer off the gutter and onto the panel
   * never leaves the wrapper - which is the whole reason the panel stays open
   * long enough to click something in it.
   */
  const [peeking, setPeeking] = useState(false);

  function toggle() {
    const next = !collapsed;
    setCollapsed(next);
    // Docking while peeked would otherwise leave `peeking` set, so the next
    // collapse would snap straight to open with no pointer near the gutter.
    setPeeking(false);
    // A year, path-wide. No `secure` - this is served over http on the laptop.
    document.cookie = `${COLLAPSE_COOKIE}=${next ? "1" : "0"}; path=/; max-age=31536000; samesite=lax`;
  }

  /**
   * One listener, two rules: the left edge opens it, and the screen closes it.
   *
   * Only while collapsed - docked there is nothing to peek. `setPeeking` with
   * the value it already holds is a no-op in React, so the common case of a
   * pointer crossing the middle of the screen costs two comparisons and no
   * render.
   *
   * Touch is excluded for the usual reason: a tap's "hover" begins and never
   * ends, so it would strand the panel open with nothing to move away. Taps
   * fall through to the toggle, which is a complete path on its own.
   */
  useEffect(() => {
    if (!collapsed) return;

    function onMove(event: PointerEvent) {
      if (event.pointerType === "touch") return;
      // The whole peek is `lg:`-only in CSS, so below it this would just churn
      // state that nothing renders.
      if (window.innerWidth < 1024) return;
      // A menu open against the panel pins it there until the menu closes.
      if (menuOpen) return;

      if (peeking) {
        if (event.clientX > PEEK_PANEL_RIGHT) setPeeking(false);
      } else if (event.clientX < PEEK_EDGE_X && event.clientY > PEEK_EDGE_TOP) {
        setPeeking(true);
      }
    }

    window.addEventListener("pointermove", onMove, { passive: true });
    return () => window.removeEventListener("pointermove", onMove);
  }, [collapsed, peeking, menuOpen]);

  // Rows in flight, because that is the only count the operator can do anything
  // about from the rail. The Review list itself reports what is waiting there;
  // re-labelling that number here would say "3 generating" when they are not.
  const { pageId } = usePageScope();
  const { data: generating } = useQuery(
    async () => (await listDrafts({ status: "generating", page_id: pageId! })).length,
    [pageId],
    {
      enabled: pageId !== null,
      intervalMs: 4_000,
      pollWhile: (count) => count === null || count > 0,
    },
  );

  // The Cart is in-memory and lives only on Sources, so without a count here a
  // Cart filled and then navigated away from is invisible. The Facebook queue
  // badges mean nothing in the Shorts workspace, and the cart is a Sources
  // thing - neither should paint a count onto a Shorts rail.
  const counts: Record<string, number | null> =
    workspace === "shorts"
      ? {}
      : {
          "/sources": cart.count || null,
          "/review": generating || null,
        };

  const toggleLabel = collapsed ? "Expand sidebar" : "Collapse sidebar";

  return (
    /**
     * The wrapper is what the shell's flex row actually sees. Collapsed it is a
     * 56px gutter holding the toggle; docked it is exactly the panel's own
     * width, so the panel sitting on top of it reads as being in the flow.
     *
     * Width is the only thing here that costs layout, and it is only ever
     * driven by a click. The hover-peek moves `transform` alone.
     */
    <div
      className={cn(
        "lg:relative lg:z-40 lg:h-screen lg:shrink-0",
        "lg:transition-[width] lg:duration-200 lg:ease-panel motion-reduce:lg:transition-none",
        collapsed ? "lg:w-14" : "lg:w-64",
      )}
    >
      {/**
       * The collapsed state's only visible control, and the target that opens
       * the peek. It lives out here rather than in the panel because the panel
       * is off-screen exactly when this is needed.
       *
       * Faded rather than unmounted: docking should not blink it out of
       * existence while the panel is still sliding across it.
       *
       * `invisible` as well as `opacity-0`, and that is not belt-and-braces.
       * Opacity alone leaves the button in the accessibility tree, so a docked
       * panel announced *two* "Collapse sidebar" buttons - this one and the
       * panel's own - and Playwright's strict mode caught it before a screen
       * reader had to. `visibility` transitions the same forgiving way as on
       * the panel, so the fade still plays in full on the way out.
       */}
      <button
        type="button"
        onClick={toggle}
        aria-label={toggleLabel}
        aria-expanded={!collapsed}
        className={cn(
          // Radii here and on the panel are written as pixels rather than
          // `rounded-xl`, on purpose. The scale in `globals.css` is derived from
          // a deliberately tight `--radius: 0.25rem`, which puts `rounded-xl` at
          // 5.6px - right for a dense table, far too hard for a card floating
          // over the screen. These two are the exception, not a new default.
          "hidden size-9 items-center justify-center rounded-[12px] border bg-sidebar text-sidebar-foreground shadow-sm",
          /**
           * `top-[26px]` is not a taste value, it is the only one that holds
           * still. The panel's own toggle ends up centred at y=44 when the
           * panel is floating: 8px top inset + 20px of `lg:pt-5` + half of its
           * 32px box. This button is 36px, so 26 + 18 puts its icon on the same
           * line - and hovering the gutter therefore slides a panel in *behind*
           * the icon you are looking at, instead of jumping it 10px down.
           */
          "lg:absolute lg:top-[26px] lg:left-3 lg:flex",
          "transition-[opacity,transform,background-color,visibility] duration-200 ease-panel motion-reduce:transition-none",
          "hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
          "focus-visible:ring-2 focus-visible:ring-sidebar-ring focus-visible:outline-none",
          // The press has to land somewhere. Without it the only feedback is
          // the panel arriving, which is 200ms after the finger was already up.
          "active:scale-[0.97]",
          collapsed ? "opacity-100" : "invisible opacity-0",
        )}
      >
        <PanelLeft className="size-4" />
      </button>

      <aside
        className={cn(
          "flex flex-col border-b bg-sidebar text-sidebar-foreground",
          /**
           * Out of the wrapper's flow on `lg`, so shrinking the wrapper to a
           * gutter slides the panel sideways instead of squeezing it. Every
           * row inside keeps its one width and never learns about collapsing.
           */
          "lg:absolute lg:w-64 lg:overflow-hidden lg:border-r lg:border-b-0",
          /**
           * The peek is a **slide**: the whole card travels in from off-screen
           * as one rigid object, so what arrives is a sidebar that moved rather
           * than a shape being filled in. A `clip-path` reveal was tried here
           * and is the wrong read - it uncovers the panel in place, column by
           * column, and the card never appears to come from anywhere.
           *
           * It is `translate` in the list, **not** `transform`, and the
           * difference is the whole animation. Tailwind v4 compiles
           * `-translate-x-*` to the standalone `translate` property rather than
           * into a `transform` matrix, so a transition naming `transform`
           * matches nothing: the panel teleports from parked to open with the
           * class change and never animates. It still ends up in the right
           * place, which is why endpoint assertions pass and only sampling the
           * box every frame catches it - `translate` on its own is compositor
           * work either way, no layout, no paint.
           *
           * `visibility` is in the list on purpose, and it is the one property
           * here that is not a number. CSS transitions special-case it: going
           * *to* hidden it stays visible for the whole duration and flips at
           * the end, going to visible it flips at the start. So the panel is on
           * screen for the whole of its exit and none of the wait before its
           * entrance - which is what stops a hidden panel from collecting tab
           * stops the moment it has finished leaving.
           */
          "lg:transition-[translate,top,bottom,border-radius,box-shadow,visibility] lg:ease-panel motion-reduce:transition-none",
          // 300ms drawing out, 200ms putting away. Slow where the user is
          // reading the panel arrive, fast where the system is just tidying up
          // after them - the duration on a state is the one used to enter it.
          "lg:duration-300",
          collapsed
            ? // Floating: inset from all three edges, rounded on every corner,
              // lifted off the screen it is covering.
              "lg:inset-y-2 lg:left-2 lg:rounded-[16px] lg:border lg:shadow-2xl"
            : "lg:inset-y-0 lg:left-0",
          // Parked just past the left edge: its own width plus the 8px inset it
          // sits at, so not even the shadow's leading edge stays in view.
          collapsed &&
            !peeking &&
            "lg:invisible lg:duration-200 lg:-translate-x-[calc(100%+0.5rem)]",
        )}
      >
        {/* `lg:pb-3`, not `pb-1`: the Page heading used to sit under this row
            and supply the gap down to the first icon. With it gone the header
            owns that spacing itself. */}
        <div className="flex h-14 shrink-0 items-center gap-2.5 px-4 whitespace-nowrap lg:h-auto lg:pt-5 lg:pb-3">
          {/**
           * `text-base`, a step up from the `text-sm` everything else in the
           * panel uses. It is the one piece of type here that is a *wordmark*
           * rather than a label, and at 14px it sat at exactly the weight of
           * the nav rows below it - present but not the first thing read.
           *
           * The mark stays at `size-5`. `logo.tsx` picked its 1.6 stroke so
           * that a 20px card lands at the same optical weight as the 16px
           * lucide icons beside it (2 × 16/20); rendering it at 24px would make
           * it 1.6px against their 1.33px and read heavier than the nav. 20px
           * beside 16px type is the right lockup proportion anyway.
           */}
          <Link
            href="/sources"
            className="flex items-center gap-2.5 text-base font-semibold tracking-tight"
          >
            <Logo className="size-5 shrink-0" />
            {/* One flex item, not two. The two halves of the wordmark are
                separate children of a `gap-2.5` flex row otherwise, so it
                renders with a 10px hole in the middle - the gap is meant for
                the space after the logo, and a bare text node is still a flex
                item. The second word is muted, the way `-agent` was. */}
            <span>
              Social <span className="text-muted-foreground">Agent</span>
            </span>
          </Link>

          <div className="ml-auto lg:hidden">
            <Generating count={generating ?? undefined} />
          </div>

          {/* The panel's own copy of the toggle - the one you reach for while
              the panel is in front of you, whether it is docked or floating.
              The gutter's copy is for when it is not.

              No tooltip: a chip naming the control you are already looking at
              is the kind of hint that only gets in the way. `aria-label`
              carries the name for anything not looking at it. */}
          <button
            type="button"
            onClick={toggle}
            aria-label={toggleLabel}
            aria-expanded={!collapsed}
            className={cn(
              GHOST_ICON,
              // After GHOST_ICON, not before: that string starts with
              // `flex`, and tailwind-merge resolves display conflicts
              // last-wins - ordered the other way the toggle reappears in
              // the mobile bar, where there is nothing to collapse.
              "hidden lg:flex",
              "lg:ml-auto",
              "active:scale-[0.97]",
            )}
          >
            {/* One icon, not a swapped pair: the panel being on screen at all
              already says which way it will go, and a glyph that changes under
              the cursor is the more distracting of the two. */}
            <PanelLeft className="size-4" />
          </button>
        </div>

        {/**
         * The workspace switch. Path-driven, sitting above the nav so the whole
         * group under it reads as one workspace.
         *
         * A dropdown rather than the two-segment pill this replaced, for the
         * reason `page-switcher.tsx` already gives about the Page control: this
         * is a **scope** control, not navigation between peers. The pill said
         * "here are two views of one thing", and Facebook and Shorts are two
         * applications that happen to share a shell - `docs/youtube-tool.md`
         * treats Shorts as separate, and every row in the nav below changes
         * when this moves. It now states which workspace you are in instead of
         * offering the pair forever, and a third one costs a menu row rather
         * than a third of the width.
         */}
        <div className="px-3 pb-1">
          <DropdownMenu open={menuOpen} onOpenChange={setMenuOpen}>
            <DropdownMenuTrigger asChild>
              <button
                type="button"
                className={cn(
                  "flex w-full items-center gap-2.5 rounded-md border px-3 py-2 text-sm font-medium whitespace-nowrap",
                  "text-sidebar-foreground transition-colors hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
                  "focus-visible:ring-2 focus-visible:ring-sidebar-ring focus-visible:outline-none",
                )}
              >
                <WorkspaceMark mark={activeWorkspace.mark} className="size-4 shrink-0" />
                <span className="truncate">{activeWorkspace.label}</span>
                <ChevronDown className="ml-auto size-3.5 shrink-0 text-muted-foreground" />
              </button>
            </DropdownMenuTrigger>

            {/* Matched to the trigger so the menu sits exactly over the control
                it came from, rather than being wider than the row it opened
                from and hanging off the panel. */}
            <DropdownMenuContent
              align="start"
              className="min-w-(--radix-dropdown-menu-trigger-width)"
            >
              {WORKSPACES.map((candidate) => (
                <DropdownMenuItem
                  key={candidate.id}
                  onSelect={() => router.push(candidate.home)}
                >
                  <WorkspaceMark mark={candidate.mark} className="size-4 shrink-0" />
                  <span className="min-w-0 flex-1 truncate">{candidate.label}</span>
                  {/* The tick holds its slot either way, so the names do not
                      shift sideways as the selection moves. */}
                  <Check
                    className={cn(
                      "size-3.5 shrink-0",
                      candidate.id !== workspace && "invisible",
                    )}
                    aria-hidden={candidate.id !== workspace}
                  />
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
        </div>

        <nav
          className={cn(
            "flex gap-1 overflow-x-auto px-3 py-2",
            // `lg:overflow-x-hidden` resets the mobile bar's horizontal scroll:
            // the panel is a column on `lg` and has nothing to scroll sideways
            // to, but a live scroll container still scrolls when something
            // inside it takes focus, which would slide the rows out of line on
            // a tab press.
            //
            // `lg:pt-3` rather than `pt-1`: with 4px here against the
            // switcher's own 4px, the destinations sat only 8px under it -
            // barely more than the 2px between the rows themselves, so the
            // switcher read as the first item in the list rather than the thing
            // that decides what the list contains. 12px makes it its own group.
            // `lg:` only, so the mobile bar's spacing is untouched.
            "lg:min-h-0 lg:flex-1 lg:flex-col lg:gap-0.5 lg:overflow-x-hidden lg:overflow-y-auto lg:pt-3 lg:pb-3",
          )}
        >
          {links.map((link) => (
            <Item
              key={link.href}
              {...link}
              active={link.href === current}
              count={counts[link.href] ?? null}
            />
          ))}

          {/* A flex column of its own on `lg`, repeating the nav's `gap-0.5`.
              The nav's gap only separates *its* children, and this whole group
              is one of them - so Settings and Global were butted flush together
              while every row above them had 2px of air. `lg:` only: below it
              the nav is a horizontal bar and this group rides in its flow. */}
          <div className="lg:mt-auto lg:flex lg:flex-col lg:gap-0.5 lg:border-t lg:pt-2">
            {/* Only mounted when there is something in flight, so the footer
                does not reserve an empty strip above Settings. */}
            {generating ? (
              <div className="hidden px-3 py-2 lg:block">
                <Generating count={generating} />
              </div>
            ) : null}
            {config.map((link) => (
              <Item
                key={link.href}
                {...link}
                active={link.href === current}
                count={null}
              />
            ))}

            {/**
             * The controls, as one line rather than two more stacked rows.
             *
             * The footer used to be four rows deep - Settings, Global, theme,
             * sign out - which read as four destinations and gave the panel a
             * heavy foot. The split that fixes it was already written down one
             * comment up: Settings and Global are *destinations*, with a URL and
             * an active state, and these two are *controls* that change nothing
             * about where you are. Rows for the first kind and a line for the
             * second makes that difference visible instead of merely true, and
             * takes a row off the stack.
             *
             * They keep their labels only as `title`/`aria-label`. A sun and a
             * door are about as legible as icons get, and this is the footer of
             * a panel whose five real destinations are all spelled out above.
             *
             * `px-1` rather than the rows' `px-3`: a `size-8` button pads its
             * own 16px glyph by 8, so 4 + 8 lands it on the same x=12 as every
             * icon above, and the same arithmetic squares the right edge up
             * with the rows' `px-3`.
             */}
            {/* Both icons together at the left, on the nav's icon column.
                They were pushed to opposite ends on the theory that proximity
                implies relationship and these two have none - which is true of
                a crowded row and wrong here: two small glyphs with 190px of
                empty panel between them read as a gap where something is
                missing, not as two unrelated controls. The separation that
                does the work is the one above them, between a labelled
                destination and an unlabelled control. */}
            <div className="flex items-center gap-1 px-1 pt-2">
              <ThemeToggle />
              <SignOut />
            </div>
          </div>
        </nav>
      </aside>
    </div>
  );
}

function WorkspaceMark({
  mark,
  className,
}: {
  mark: "facebook" | "youtube";
  className?: string;
}) {
  const Glyph = mark === "facebook" ? FacebookMark : YoutubeMark;
  return <Glyph className={className} />;
}

function Item({
  href,
  label,
  icon: Icon,
  active,
  count,
}: {
  href: string;
  label: string;
  icon: LucideIcon;
  active: boolean;
  count: number | null;
}) {
  return (
    <Link
      href={href}
      aria-current={active ? "page" : undefined}
      className={cn(
        /**
         * 10px, not the `rounded-md` (3px) the rest of the app uses and not the
         * panel's own 16px either.
         *
         * The highlight is a shape drawn *inside* a rounded card, and a 3px
         * corner inside a 16px one reads as two unrelated radii stacked - which
         * is why this moved at all. But matching the card exactly overshoots in
         * the other direction: the row is 36px tall, so 18px is a full pill and
         * 16px is close enough to one to read as a lozenge rather than a
         * highlighted row. 10px is unmistakably rounded and unmistakably not a
         * pill.
         *
         * See the note on `--radius` in `globals.css`: the tight global scale is
         * for dense tables, and this is the one place in the panel that has to
         * answer to the card around it instead.
         */
        "relative flex shrink-0 items-center gap-2.5 rounded-[10px] px-3 py-2 text-sm whitespace-nowrap transition-colors",
        // Full-contrast whether active or not. Greying the inactive items made
        // the icons look soft and out of focus rather than merely secondary;
        // the active one is already carried by its fill and weight, so it does
        // not need the others dimmed to stand out.
        /**
         * Hover is half the active fill, not the same fill.
         *
         * Both states used `bg-sidebar-accent` outright, so running the pointer
         * down the list lit each row exactly as though it were the current
         * screen - the one thing the fill is there to say. `/50` composites the
         * same colour at half strength over `--sidebar`, which lands it between
         * the panel and the active row in both themes without inventing a
         * token: light goes 0.985 → 0.978 → 0.970, dark 0.18 → 0.22 → 0.26.
         *
         * No `hover:text-*`. `--sidebar-accent-foreground` is *lighter* than
         * `--sidebar-foreground` (0.205 vs 0.145 in light), so the old hover
         * faded the label as the pointer arrived - backwards for a state whose
         * whole job is to say "this responds". The active row can afford it
         * because `font-medium` carries it; a hover cannot.
         */
        active
          ? "bg-sidebar-accent font-medium text-sidebar-accent-foreground"
          : "text-sidebar-foreground hover:bg-sidebar-accent/50",
      )}
    >
      <Icon className="size-4 shrink-0" />
      <span className="truncate">{label}</span>

      {count ? (
        <span className="ml-auto pl-2 text-xs tabular-nums text-muted-foreground">
          {count}
        </span>
      ) : null}
    </Link>
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
