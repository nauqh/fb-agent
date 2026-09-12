"use client";

import { useRouter } from "next/navigation";
import { LogOut } from "lucide-react";

/**
 * Sign out, as an icon at the far end of the panel's footer line.
 *
 * Shaped after `ThemeToggle` down to the class list, because it shares that
 * line and the two glyphs have to be the same size and weight.
 *
 * It sits at the *opposite* end of the line rather than next to the theme
 * toggle. Proximity reads as relationship, and these two have none: one is a
 * display preference, the other ends the session. The gap is the point.
 *
 * A button rather than a link: `/auth/logout` is POST only, so that a prefetch
 * or an image tag cannot sign the operator out by being loaded.
 */
export function SignOut() {
  const router = useRouter();

  async function signOut() {
    await fetch("/auth/logout", { method: "POST" });
    router.replace("/login");
    // The cookie is gone, but the rendered tree behind it is still cached.
    router.refresh();
  }

  return (
    <button
      type="button"
      onClick={() => void signOut()}
      aria-label="Sign out"
      title="Sign out"
      className={CONTROL_ICON}
    >
      <LogOut className="size-4" />
    </button>
  );
}

/** The line's icon-button shape. See the note on the copy in `theme-toggle`. */
const CONTROL_ICON =
  "flex size-8 shrink-0 items-center justify-center rounded-md text-sidebar-foreground " +
  "transition-[background-color,color,transform] duration-100 ease-out " +
  "hover:bg-sidebar-accent hover:text-sidebar-accent-foreground active:scale-[0.97] " +
  "focus-visible:ring-2 focus-visible:ring-sidebar-ring focus-visible:outline-none";
