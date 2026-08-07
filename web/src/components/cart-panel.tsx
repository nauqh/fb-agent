"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2, Sparkles, X } from "lucide-react";
import { toast } from "sonner";

import { generate } from "@/lib/api/drafts";
import { listPages } from "@/lib/api/pages";
import { sourceKey, useCart } from "@/lib/cart";
import { useQuery } from "@/lib/use-query";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

/**
 * The Cart, pinned beside the source grids. Starts the run itself.
 *
 * It used to navigate to a `/generate` screen instead. That screen showed the
 * same cart again, a Page that could not be changed, and `N sources × 1 page =
 * N drafts` — arithmetic that multiplies by one. It was a confirmation step for
 * a decision with a single possible answer, and its stated reason (design.md:
 * seeing *how many* against *which Page* rather than burying it in a picker)
 * was written for the old app's ten brands. With one Page there is nothing to
 * pick, so the count moved onto the button and the screen went.
 *
 * The topic field was the only thing on it that existed nowhere else, so it
 * lives here now, in the empty state — which is exactly when it applies.
 */
export function CartPanel() {
  const cart = useCart();
  const router = useRouter();
  const [topic, setTopic] = useState("");
  const [running, setRunning] = useState(false);

  const { data: pages } = useQuery(() => listPages(), []);
  const page = pages?.[0];

  // A topic run and a source run are exclusive: a ticked Cart is what the
  // operator meant, and the topic box is only reachable while it is empty.
  const usingTopic = cart.count === 0;
  const draftCount = usingTopic ? (topic.trim() ? 1 : 0) : cart.count;

  async function run() {
    if (!page || draftCount === 0) return;
    setRunning(true);
    try {
      const ids = await generate({
        // By value: generate is the only thing that writes a source_item row,
        // so it needs the item rather than a pointer to one.
        sources: usingTopic ? [] : cart.items,
        page_ids: [page.id],
        topic: usingTopic ? topic.trim() : undefined,
      });
      cart.clear();
      setTopic("");
      toast.success(`${ids.length} draft${ids.length === 1 ? "" : "s"} generating.`, {
        description: "Progress is on the Review screen.",
      });
      router.push(`/review/${ids[0]}`);
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "Generate failed");
    } finally {
      setRunning(false);
    }
  }

  // No fetch for the items: the Cart holds them, so there is nothing to
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
          <div className="space-y-4 px-2 py-6">
            <p className="text-center text-xs text-muted-foreground">
              Tick a competitor post, a tweet or an RSS item.
            </p>
            <div className="space-y-2 border-t pt-4">
              <Label htmlFor="topic" className="text-xs">
                Or write from a topic
              </Label>
              <Input
                id="topic"
                value={topic}
                onChange={(event) => setTopic(event.target.value)}
                placeholder="The Great Molasses Flood, Boston 1919"
                className="text-xs"
              />
              <p className="text-[11px] text-muted-foreground">
                A topic-only Draft has no Source Item — nothing binds the story except the
                topic itself.
              </p>
            </div>
          </div>
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
        {/* The count is on the button because it is the only thing the removed
            screen showed that the operator could not already see, and this is
            now the click that spends money. */}
        <Button
          className="w-full bg-gold text-gold-foreground hover:bg-gold/90"
          disabled={draftCount === 0 || running || !page}
          onClick={run}
        >
          {running ? (
            <Loader2 className="size-4 animate-spin" />
          ) : (
            <Sparkles className="size-4" />
          )}
          {draftCount === 0
            ? "Generate"
            : `Generate ${draftCount} draft${draftCount === 1 ? "" : "s"}`}
        </Button>
      </div>
    </aside>
  );
}
