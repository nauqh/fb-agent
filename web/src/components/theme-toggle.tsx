"use client";

import { Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";

import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

/**
 * Light ⇄ dark, as a row in the rail's footer.
 *
 * **Nothing here reads the theme during render, and that is the whole design.**
 * The active theme lives in localStorage, which the server cannot see, so a
 * component that renders `theme === "dark" ? <Moon/> : <Sun/>` renders the
 * wrong branch on the server and hydrates into a mismatch. The usual fix is a
 * `mounted` flag set in an effect — that is a set-state-in-effect, which this
 * codebase lints against, and it also blanks the control for a frame.
 *
 * So both icons and both labels are always rendered, and `dark:` decides which
 * one is visible. next-themes puts `.dark` on `<html>` from a blocking script
 * before first paint, so the right one is showing on the very first frame and
 * the server markup was never wrong to begin with. `resolvedTheme` is read only
 * inside the click handler, which cannot run before hydration.
 *
 * `aria-label` stays "Toggle theme" rather than naming the target state, for
 * the same reason: a theme-dependent string in the markup is the mismatch this
 * is avoiding.
 */
export function ThemeToggle({ collapsed }: { collapsed: boolean }) {
  const { resolvedTheme, setTheme } = useTheme();

  const button = (
    <button
      type="button"
      onClick={() => setTheme(resolvedTheme === "dark" ? "light" : "dark")}
      aria-label="Toggle theme"
      className={cn(
        // Deliberately the same shape as `Item` in the sidebar: `px-3` constant
        // so the icon sits at the same x in both rail widths, and the row clips
        // its own faded label rather than letting it reach the nav's scroll box.
        "relative flex w-full shrink-0 items-center gap-2.5 rounded-md px-3 py-2 text-sm whitespace-nowrap transition-colors",
        "text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
        collapsed && "lg:overflow-hidden",
      )}
    >
      <span className="relative shrink-0">
        <Sun className="size-4 dark:hidden" />
        <Moon className="hidden size-4 dark:block" />
      </span>

      {/* Faded, not `hidden` — same reasoning as the nav labels: `hidden` is
          instant and leaves the rail shrinking around empty space. */}
      <span
        className={cn(
          "truncate transition-opacity duration-300 ease-linear",
          collapsed && "lg:opacity-0",
        )}
      >
        <span className="dark:hidden">Light</span>
        <span className="hidden dark:inline">Dark</span>
      </span>
    </button>
  );

  if (!collapsed) return button;

  return (
    <Tooltip>
      <TooltipTrigger asChild>{button}</TooltipTrigger>
      <TooltipContent side="right">Toggle theme</TooltipContent>
    </Tooltip>
  );
}
