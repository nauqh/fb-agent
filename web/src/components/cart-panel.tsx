"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2, Sparkles, X } from "lucide-react";
import { toast } from "sonner";

import { generate } from "@/lib/api/drafts";
import { sourceKey, useCart } from "@/lib/cart";
import { usePageScope } from "@/lib/page-scope";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

/**
 * The Cart, a dock under the source grids. Starts the run itself.
 *
 * It was a 320px column beside the grid, which cost the grid 344px of width
 * for a panel that is empty most of the time. As a dock it costs one row of
 * height and the grid gets the full width — three columns at 1440 instead of
 * two, and four above 1900.
 *
 * Always on screen, never hidden when empty, for two reasons: the topic field
 * below only applies while the Cart *is* empty, so a dock that hides would
 * stranded it in some header; and Generate is the screen's primary action, which
 * was the one thing the pinned column got right and a scrolling Cart would lose.
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

  // The switcher's Page, not `pages[0]`. Generate writes `draft.page_id`, so
  // this is the one place where reading the wrong Page produces a row that
  // looks right and is not.
  const { page } = usePageScope();

  // A topic run and a source run are exclusive: a ticked Cart is what the
  // operator meant, and the topic box is only reachable while it is empty.
  const usingTopic = cart.count === 0;
  const draftCount = usingTopic ? (topic.trim() ? 1 : 0) : cart.count;

  /**
   * Use the sources' own pictures instead of buying heroes.
   *
   * Offered only when the Cart actually holds some — the option is meaningless
   * against a topic run, which has no Source Item, and dishonest against items
   * with no `image_url`, where every draft would come back carrying a warning
   * instead of a picture.
   *
   * Not sticky between runs. It is a property of *these* sources rather than a
   * preference: the next cart may be competitor posts with nothing to take.
   */
  const [heroFromSource, setHeroFromSource] = useState(false);
  /**
   * RSS only, mirroring the server, which refuses the rest.
   *
   * A competitor post's picture is a rival page's own creative and a tweet's
   * belongs to whoever posted it, so reusing either as our hero is reposting
   * their content under our watermark. A feed image accompanies a story we are
   * retelling. The client asked for "the image provided by the RSS feed", and
   * the narrower reading is also the defensible one.
   */
  const withPictures = cart.items.filter(
    (item) => item.kind === "rss" && item.image_url,
  ).length;
  const offerSourceHero = !usingTopic && withPictures > 0;

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
        hero_from_source: offerSourceHero && heroFromSource,
      });
      cart.clear();
      setTopic("");
      setHeroFromSource(false);
      toast.success(`${ids.length} draft${ids.length === 1 ? "" : "s"} generating.`, {
        description: "Progress is on the Review screen.",
      });
      // The queue, not the first draft. A run can produce several, and the one
      // that happened to be first is not more interesting than the rest — the
      // list shows all of them filling in, and the drawer would cover it.
      router.push("/review");
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "Generate failed");
    } finally {
      setRunning(false);
    }
  }

  // No fetch for the items: the Cart holds them, so there is nothing to
  // resolve. This used to call GET /sources?ids= to turn ids back into rows.
  return (
    <aside className="flex shrink-0 items-center gap-3 rounded-lg border p-2">
      {cart.count === 0 ? (
        <>
          <Label htmlFor="topic" className="shrink-0 pl-1 text-xs text-muted-foreground">
            Tick a source, or write from a topic
          </Label>
          <Input
            id="topic"
            value={topic}
            onChange={(event) => setTopic(event.target.value)}
            placeholder="The Great Molasses Flood, Boston 1919"
            className="max-w-sm flex-1 text-xs"
          />
          {/* The distinction the operator is actually making by typing here, so
              it stays next to the box rather than moving to a tooltip. */}
          <p className="hidden min-w-0 flex-1 truncate text-[11px] text-muted-foreground xl:block">
            A topic-only Draft has no Source Item — nothing binds the story except the topic
            itself.
          </p>
        </>
      ) : (
        <>
          <span className="shrink-0 pl-1 text-sm font-medium">
            Cart <span className="text-muted-foreground">· {cart.count}</span>
          </span>

          {/* The ticked items, as chips. A row rather than the column's stacked
              list: the dock is one row tall, and the author is what identifies
              a Source Item at a glance — the body text needed two lines to say
              less. Scrolls sideways rather than wrapping, so the dock's height
              cannot depend on how many are ticked. */}
          <ul className="flex min-w-0 flex-1 items-center gap-1.5 overflow-x-auto">
            {cart.items.map((item) => (
              <li
                key={sourceKey(item)}
                className="flex shrink-0 items-center gap-1 rounded-full border bg-muted/40 py-1 pr-1 pl-2.5"
              >
                <span className="max-w-40 truncate text-xs" title={item.text}>
                  {item.author}
                </span>
                <button
                  type="button"
                  onClick={() => cart.remove(item)}
                  className="rounded-full p-0.5 text-muted-foreground hover:text-foreground"
                  aria-label={`Remove ${item.author} from cart`}
                >
                  <X className="size-3" />
                </button>
              </li>
            ))}
          </ul>

          {/* Beside Generate, not in a settings screen: it changes what the
              next click costs, so it belongs where the cost is incurred. The
              count is the honest part — it says how many of the ticked items
              can actually supply one, which is the difference between "free
              heroes" and "some free heroes and some warnings". */}
          {offerSourceHero ? (
            <label
              className="flex shrink-0 cursor-pointer items-center gap-1.5 text-xs text-muted-foreground"
              title="Use each source's own photograph instead of generating one. No Gemini call, and the rights are the publisher's."
            >
              <input
                type="checkbox"
                checked={heroFromSource}
                onChange={(event) => setHeroFromSource(event.target.checked)}
                className="size-3.5 cursor-pointer accent-primary"
              />
              Use source picture
              {withPictures < cart.count ? (
                <span className="tabular-nums">
                  ({withPictures}/{cart.count})
                </span>
              ) : null}
            </label>
          ) : null}

          <Button variant="ghost" size="sm" className="shrink-0" onClick={cart.clear}>
            Clear
          </Button>
        </>
      )}

      {/* The count is on the button because it is the only thing the removed
          screen showed that the operator could not already see, and this is
          now the click that spends money. */}
      <Button
        className="shrink-0 bg-gold text-gold-foreground hover:bg-gold/90"
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
    </aside>
  );
}
