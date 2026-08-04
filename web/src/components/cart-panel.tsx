"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { Sparkles, X } from "lucide-react";

import { sourceKey, useCart } from "@/lib/cart";
import { Button } from "@/components/ui/button";
import { isFactual } from "@/lib/types";

/**
 * The Cart, pinned beside the source grids.
 *
 * Its Generate button navigates to /generate rather than opening a picker
 * dialog: the run needs a Quota check and a source × page count in front of the
 * operator, and neither belongs in a modal.
 */
export function CartPanel() {
  const cart = useCart();
  const router = useRouter();

  // No fetch: the Cart holds the items themselves, so there is nothing to
  // resolve. This used to call GET /sources?ids= to turn ids back into rows.
  return (
    <aside className="flex h-full min-h-0 w-full flex-col rounded-lg border">
      <div className="flex items-center justify-between border-b px-4 py-3">
        <h2 className="text-sm font-medium">
          Cart{cart.count > 0 ? <span className="text-muted-foreground"> · {cart.count}</span> : null}
        </h2>
        {cart.count > 0 ? (
          <Button variant="ghost" size="sm" className="-mr-2 h-7" onClick={cart.clear}>
            Clear
          </Button>
        ) : null}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto p-2">
        {cart.count === 0 ? (
          <p className="px-2 py-8 text-center text-xs leading-relaxed text-muted-foreground">
            Tick a competitor post, a tweet or an RSS item.
            <br />
            Ticking a live one is what writes its row.
          </p>
        ) : (
          <ul className="space-y-1">
            {cart.items.map((item) => (
              <li
                key={sourceKey(item)}
                className="group flex items-start gap-2 rounded-md p-2 hover:bg-muted/60"
              >
                <div className="min-w-0 flex-1">
                  <p className="truncate text-xs font-medium">{item.author}</p>
                  <p className="line-clamp-2 text-xs text-muted-foreground">{item.text}</p>
                  <p className="pt-1 text-[10px] uppercase tracking-wide text-muted-foreground/70">
                    {isFactual(item.kind) ? "binds the story" : "style only"}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => cart.remove(item)}
                  className="rounded p-0.5 text-muted-foreground opacity-0 transition-opacity hover:text-foreground group-hover:opacity-100"
                  aria-label="Remove from cart"
                >
                  <X className="size-3.5" />
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="border-t p-3">
        <Button
          className="w-full bg-gold text-gold-foreground hover:bg-gold/90"
          disabled={cart.count === 0}
          onClick={() => router.push("/generate")}
        >
          <Sparkles className="size-4" />
          Generate
        </Button>
        <p className="pt-2 text-center text-[11px] text-muted-foreground">
          or{" "}
          <Link href="/generate" className="underline underline-offset-2">
            write from a topic
          </Link>
        </p>
      </div>
    </aside>
  );
}
