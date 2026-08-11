"use client";

import { useRouter } from "next/navigation";
import { LogOut } from "lucide-react";

import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

/**
 * Sign out, as a row in the rail's footer.
 *
 * Shaped after `ThemeToggle` down to the class list, because it sits directly
 * beneath it and the icons have to land in the same column at both rail widths.
 *
 * A button rather than a link: `/auth/logout` is POST only, so that a prefetch
 * or an image tag cannot sign the operator out by being loaded.
 */
export function SignOut({ collapsed }: { collapsed: boolean }) {
  const router = useRouter();

  async function signOut() {
    await fetch("/auth/logout", { method: "POST" });
    router.replace("/login");
    // The cookie is gone, but the rendered tree behind it is still cached.
    router.refresh();
  }

  const button = (
    <button
      type="button"
      onClick={() => void signOut()}
      aria-label="Sign out"
      className={cn(
        "relative flex w-full shrink-0 items-center gap-2.5 rounded-md px-3 py-2 text-sm whitespace-nowrap transition-colors",
        "text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
        collapsed && "lg:overflow-hidden",
      )}
    >
      <LogOut className="size-4 shrink-0" />
      <span
        className={cn(
          "truncate transition-opacity duration-300 ease-linear",
          collapsed && "lg:opacity-0",
        )}
      >
        Sign out
      </span>
    </button>
  );

  if (!collapsed) return button;

  return (
    <Tooltip>
      <TooltipTrigger asChild>{button}</TooltipTrigger>
      <TooltipContent side="right">Sign out</TooltipContent>
    </Tooltip>
  );
}
