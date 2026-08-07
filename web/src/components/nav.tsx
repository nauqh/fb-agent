"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { listDrafts } from "@/lib/api/drafts";
import { useCart } from "@/lib/cart";
import { useQuery } from "@/lib/use-query";
import { cn } from "@/lib/utils";

const LINKS = [
  { href: "/sources", label: "Sources" },
  { href: "/review", label: "Review" },
  { href: "/settings", label: "Settings" },
] as const;

export function Nav() {
  const pathname = usePathname();
  const cart = useCart();

  // Drafts still needing a decision, and rows currently in flight — the two
  // numbers that tell the operator there is work waiting without opening the
  // screen.
  const { data: queue } = useQuery(
    async () => {
      const [review, generating] = await Promise.all([
        listDrafts({ status: "review" }),
        listDrafts({ status: "generating" }),
      ]);
      return { review: review.length, generating: generating.length };
    },
    [],
    {
      intervalMs: 4_000,
      pollWhile: (counts) => counts === null || counts.generating > 0,
    },
  );

  return (
    <header className="sticky top-0 z-40 border-b bg-background/80 backdrop-blur">
      <div className="mx-auto flex h-14 w-full max-w-[1600px] items-center gap-8 px-6">
        <Link href="/sources" className="text-sm font-semibold tracking-tight">
          fb<span className="text-muted-foreground">-agent</span>
        </Link>

        <nav className="flex items-center gap-1">
          {LINKS.map((link) => {
            const active = pathname.startsWith(link.href);
            const badge = link.href === "/review" ? queue?.review || null : null;

            return (
              <Link
                key={link.href}
                href={link.href}
                className={cn(
                  "relative rounded-md px-3 py-1.5 text-sm transition-colors",
                  active
                    ? "text-foreground"
                    : "text-muted-foreground hover:text-foreground",
                )}
              >
                <span className="inline-flex items-center gap-1.5">
                  {link.label}
                  {badge ? (
                    <span className="tabular-nums text-xs text-muted-foreground">
                      · {badge}
                    </span>
                  ) : null}
                </span>
                {active ? (
                  <span className="absolute inset-x-3 -bottom-[13px] h-px bg-foreground" />
                ) : null}
              </Link>
            );
          })}
        </nav>

        <div className="ml-auto flex items-center gap-3 text-xs text-muted-foreground">
          {/* The Cart used to be a nav item, and its count rode on that link.
              With the Generate screen gone the Cart lives only on Sources, so
              without this a Cart filled and then navigated away from is
              invisible — and it is in-memory state that a reload discards. */}
          {cart.count ? (
            <Link href="/sources" className="hover:text-foreground">
              Cart · {cart.count}
            </Link>
          ) : null}
          {queue?.generating ? (
            <span className="inline-flex items-center gap-1.5">
              <span className="size-1.5 animate-pulse rounded-full bg-gold" />
              {queue.generating} generating
            </span>
          ) : null}
          <span className="hidden sm:inline">History Retraced</span>
        </div>
      </div>
    </header>
  );
}
