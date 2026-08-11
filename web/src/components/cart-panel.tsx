"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Loader2, Sparkles, X } from "lucide-react";
import { toast } from "sonner";

import { generate } from "@/lib/api/drafts";
import { sourceKey, useCart } from "@/lib/cart";
import { usePageScope } from "@/lib/page-scope";
import { Button } from "@/components/ui/button";

/**
 * The Cart, a dock under the source grids. Starts the run itself.
 *
 * It was a 320px column beside the grid, which cost the grid 344px of width
 * for a panel that is empty most of the time. As a dock it costs one row of
 * height and the grid gets the full width — three columns at 1440 instead of
 * two, and four above 1900.
 *
 * Always on screen, never hidden when empty. Generate is the screen's primary
 * action — the one thing the pinned column got right and a scrolling Cart would
 * lose — and a dock that appeared on the first tick would push the grid up under
 * the cursor that just ticked.
 *
 * It used to navigate to a `/generate` screen instead. That screen showed the
 * same cart again, a Page that could not be changed, and `N sources × 1 page =
 * N drafts` — arithmetic that multiplies by one. It was a confirmation step for
 * a decision with a single possible answer, and its stated reason (design.md:
 * seeing *how many* against *which Page* rather than burying it in a picker)
 * was written for the old app's ten brands. With one Page there is nothing to
 * pick, so the count moved onto the button and the screen went.
 *
 * The topic field was the only thing on that screen which existed nowhere else,
 * so it moved into this dock's empty state. It has since moved again, to
 * `/manual`, at the client's request — they want a destination they can grow,
 * and a strip in another screen's footer has nowhere to grow. The dock's empty
 * state points at it rather than duplicating it.
 */
export function CartPanel() {
  const cart = useCart();
  const router = useRouter();
  const [running, setRunning] = useState(false);

  // The switcher's Page, not `pages[0]`. Generate writes `draft.page_id`, so
  // this is the one place where reading the wrong Page produces a row that
  // looks right and is not.
  const { page } = usePageScope();

  // One draft per ticked source. The topic run is `/manual`'s now, so this
  // dock no longer has two modes to keep apart.
  const draftCount = cart.count;

  /**
   * Use the sources' own pictures instead of buying heroes.
   *
   * Offered only when the Cart actually holds some — it would be dishonest
   * against items with no `image_url`, where every draft would come back
   * carrying a warning instead of a picture.
   *
   * Not sticky between runs. It is a property of *these* sources rather than a
   * preference: the next cart may be competitor posts with nothing to take.
   */
  const [heroFromSource, setHeroFromSource] = useState(false);
  /**
   * Produce text-only drafts. The one generate path that costs nothing: no
   * hero is bought and nothing is composited.
   *
   * Mutually exclusive with the source picture, and the UI enforces it rather
   * than letting the server pick a winner — asking for the feed's photograph
   * and for no photograph is a contradiction, not a preference.
   */
  const [noImage, setNoImage] = useState(false);
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
  const offerSourceHero = withPictures > 0;

  async function run() {
    if (!page || draftCount === 0) return;
    setRunning(true);
    try {
      const ids = await generate({
        // By value: generate is the only thing that writes a source_item row,
        // so it needs the item rather than a pointer to one.
        sources: cart.items,
        page_ids: [page.id],
        hero_from_source: offerSourceHero && heroFromSource && !noImage,
        no_image: noImage,
      });
      cart.clear();
      setHeroFromSource(false);
      setNoImage(false);
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
        // The topic box lived here and is on `/manual` now — a move at the
        // client's request, not a copy, so there is one place to type a topic.
        // The dock keeps its space rather than collapsing: it is the screen's
        // primary action, and a row that appears on the first tick would push
        // the grid up under the cursor that just ticked.
        <p className="min-w-0 flex-1 pl-1 text-xs text-muted-foreground">
          Tick a source to generate from it, or write from a topic on{" "}
          <Link href="/manual" className="underline underline-offset-2">
            Manual
          </Link>
          .
        </p>
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
          {/* Text only. Beside the other picture option because they answer
              the same question — where does the image come from — and one of
              the answers is "there isn't one". */}
          <label
            className="flex shrink-0 cursor-pointer items-center gap-1.5 text-xs text-muted-foreground"
            title="Produce drafts with no picture at all. Nothing is generated, so this run costs nothing."
          >
            <input
              type="checkbox"
              checked={noImage}
              onChange={(event) => {
                setNoImage(event.target.checked);
                if (event.target.checked) setHeroFromSource(false);
              }}
              className="size-3.5 cursor-pointer accent-primary"
            />
            No image
          </label>

          {offerSourceHero && !noImage ? (
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
