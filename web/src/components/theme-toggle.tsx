"use client";

import { Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";

/**
 * Light ⇄ dark, as a row in the panel's footer.
 *
 * **Nothing here reads the theme during render, and that is the whole design.**
 * The active theme lives in localStorage, which the server cannot see, so a
 * component that renders `theme === "dark" ? <Moon/> : <Sun/>` renders the
 * wrong branch on the server and hydrates into a mismatch. The usual fix is a
 * `mounted` flag set in an effect - that is a set-state-in-effect, which this
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
export function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme();

  return (
    <button
      type="button"
      onClick={() => setTheme(resolvedTheme === "dark" ? "light" : "dark")}
      aria-label="Toggle theme"
      // `title` rather than a `Tooltip`: the label is gone now that this is an
      // icon, and the native one costs no component, no portal and no timer for
      // a control opened about twice a year.
      title="Toggle theme"
      // A square in the footer's control line, not a row. Sized and tinted like
      // the panel's other icon buttons so the line reads as one set.
      className={CONTROL_ICON}
    >
      <Sun className="size-4 dark:hidden" />
      <Moon className="hidden size-4 dark:block" />
    </button>
  );
}

/**
 * The footer line's icon-button shape. `SignOut` carries the same string, the
 * way these two files have always mirrored each other - a shared constant would
 * have to live in one of them or in `sidebar.tsx`, and importing it back from
 * `sidebar.tsx` is a cycle.
 *
 * `size-8` in a `px-1` line puts the 16px glyph at the same x as every nav icon
 * above it, so the footer reads as the bottom of the same column rather than a
 * separate strip.
 *
 * `active:scale` is on a 100ms curve because the press is the feedback - the
 * theme flip itself is instant and has nothing to animate.
 */
const CONTROL_ICON =
  "flex size-8 shrink-0 items-center justify-center rounded-md text-sidebar-foreground " +
  "transition-[background-color,color,transform] duration-100 ease-out " +
  "hover:bg-sidebar-accent hover:text-sidebar-accent-foreground active:scale-[0.97] " +
  "focus-visible:ring-2 focus-visible:ring-sidebar-ring focus-visible:outline-none";
