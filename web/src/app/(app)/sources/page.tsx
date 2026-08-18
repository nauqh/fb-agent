"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { AlertTriangle, Loader2, RefreshCw, Search } from "lucide-react";
import { toast } from "sonner";

import { CartPanel } from "@/components/cart-panel";
import { ScreenHeader } from "@/components/screen";
import { QueryError } from "@/components/query-error";
import { SourceCard } from "@/components/source-card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { Loading } from "@/components/loading";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  getCompetitorReach,
  getRss,
  getCompetitorPosts,
  getTweet,
} from "@/lib/api/sources";
import type { CompetitorReach, SourceSort } from "@/lib/api/sources";
import type { LiveSourceItem } from "@/lib/fixtures/sources";
import { useCart } from "@/lib/cart";
import { usePageScope } from "@/lib/page-scope";
import { emit } from "@/lib/store";
import { useQuery } from "@/lib/use-query";

// The Page every competitor set and feed list belongs to used to be `const
// PAGE_ID = 1`. It comes from the switcher now — the competitor sets do not
// overlap at all (18 pages against 24, zero in common) and neither do the
// feeds, so a stale id here would show one Page's grid under another's name.

export default function SourcesScreen() {
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <ScreenHeader title="Sources" />

      {/* One column now. The Cart used to be a 320px column here, which cost
          the grid 344px of width for a panel that is empty most of the time;
          it is a dock under the tabs instead, and the grid has the full width. */}
      <Tabs defaultValue="competitors" className="flex min-h-0 flex-1 flex-col gap-4">
        {/* `*:` reaches the triggers, so the width and padding live in one
            place instead of being repeated on each of the three. */}
        <TabsList className="shrink-0 gap-1.5 p-1 *:min-w-28 *:px-4">
          <TabsTrigger value="competitors">Competitors</TabsTrigger>
          <TabsTrigger value="tweets">Tweets</TabsTrigger>
          <TabsTrigger value="rss">RSS</TabsTrigger>
        </TabsList>

        {/* `pr-3` on each pane: these own the scrollbar, and without it the
            card grid runs right up against the bar. Inside the scroller, so
            it holds the content off the bar rather than moving the bar. */}
        <TabsContent value="competitors" className="min-h-0 flex-1 overflow-y-auto pr-3">
          <CompetitorsTab />
        </TabsContent>
        <TabsContent value="tweets" className="min-h-0 flex-1 overflow-y-auto pr-3">
          <TweetsTab />
        </TabsContent>
        <TabsContent value="rss" className="min-h-0 flex-1 overflow-y-auto pr-3">
          <RssTab />
        </TabsContent>

        <CartPanel />
      </Tabs>
    </div>
  );
}

function CompetitorsTab() {
  const cart = useCart();
  const { pageId } = usePageScope();
  // This Page's competitors, and no control here to widen it.
  //
  // There was a scope filter on this tab for exactly one commit. It duplicated
  // the Page switcher a few pixels away, and it asked a question Settings now
  // answers: which competitors a Page reads is an assignment, made once, not a
  // filter re-picked every session. The old app filtered at browse time because
  // it had no assignment to make.
  //
  // `pageId` gates the query: null means the Pages have not landed yet, and
  // firing against a guessed id would show the wrong Page's competitors for a
  // beat before correcting itself.
  /**
   * Reactions by default, recency on request (client feedback G1).
   *
   * Reactions is what Metricool's own Competitors tab shows and what
   * `fetch_competitor_posts` has always sorted by — the grid read was the only
   * thing throwing that order away. Newest-first was showing the weakest posts:
   * measured on History Retraced's real pool, the newest 60 topped out at 2,031
   * reactions while the same week held one at 42,738.
   *
   * Held here rather than in the URL. It is a way of reading one grid, not a
   * place to link someone to, and it re-queries the server rather than
   * re-sorting on the client — the ranking decides which 60 of 1,244 rows come
   * back at all.
   */
  const [sort, setSort] = useState<SourceSort>("reactions");

  const { data, loading, error, refresh } = useQuery(
    () => getCompetitorPosts(pageId === null ? [] : [pageId], false, sort),
    [pageId, sort],
    { enabled: pageId !== null },
  );
  const [syncing, setSyncing] = useState(false);

  /**
   * The two things the grid itself cannot say: why it is empty, and how much of
   * what it is showing has already been used.
   *
   * Local counts, no Metricool call — see `get_competitor_reach`. Read on every
   * grid load rather than only when empty, because the used total is needed
   * precisely when there *are* rows.
   */
  const { data: reach, error: reachError } = useQuery(
    () => getCompetitorReach(pageId === null ? [] : [pageId]),
    [pageId],
    { enabled: pageId !== null },
  );

  /**
   * How many used sources are actually marked on screen.
   *
   * `used` is computed over the rows the grid returns — 60 — while the pool
   * behind it is 808 for History Retraced. Measured 2026-08-17: 31 drafts
   * generated from chosen posts against 2 markers visible, and on Bodybuilding
   * Tips N Tricks 3 against **zero**. Ticking a post, generating, and coming
   * back to no marker anywhere is what "NONE from chosen posts were generated"
   * describes, so the difference between these two numbers is said out loud
   * rather than left to be inferred from a grid that looks untouched.
   */
  const usedInView = data?.filter((item) => item.used).length ?? 0;

  /**
   * Syncing is the operator's call, not the tab's.
   *
   * Opening the tab used to cost ~5.5s and 1.6MB to pull 500 posts and show 60,
   * against a seven-day window that gains about three an hour. The server syncs
   * on its own only when it has nothing stored.
   */
  async function sync() {
    if (pageId === null) return;
    setSyncing(true);
    try {
      await getCompetitorPosts([pageId], true);
      emit();
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "Sync failed");
    } finally {
      setSyncing(false);
    }
  }

  return (
    <>
      <div className="flex items-center justify-between gap-3 pb-3">
        <p className="text-xs text-muted-foreground">
          {sort === "reactions"
            ? "Synced from Metricool, best of the last 7 days first."
            : "Synced from Metricool, newest first."}{" "}
          Which competitors this Page reads is set on Settings.
          {reach && reach.used_posts > 0 ? (
            <>
              {" "}
              <span className="text-foreground">
                {reach.used_posts} source{reach.used_posts === 1 ? " has" : "s have"}{" "}
                been generated from
              </span>
              {usedInView < reach.used_posts
                ? ` — ${usedInView === 0 ? "none of them is" : `only ${usedInView} of them are`} marked below.`
                : ", all marked below."}
            </>
          ) : null}
        </p>

        <div className="flex shrink-0 items-center gap-2">
          {/* Two words, not a dropdown: there are exactly two orders and both
              fit. The window in the hint above moves with the choice because
              the two are not independent — ranking by reactions is bounded to
              seven days server-side so that a post that went viral in July
              cannot hold the top of the grid forever.

              The shared pill shell (`ui/tabs.tsx`), not a pair of bordered
              boxes: this is a choice between alternatives, which is what every
              other such control in the app now looks like. The old active
              state was `bg-primary/10`, a near-white tint that read as barely
              distinguishable from the inactive one. */}
          <Tabs value={sort} onValueChange={(next) => setSort(next as SourceSort)}>
            <TabsList className="w-fit" aria-label="Sort competitor posts">
              <TabsTrigger value="reactions">Reactions</TabsTrigger>
              <TabsTrigger value="newest">Newest</TabsTrigger>
            </TabsList>
          </Tabs>

          {/* `h-7` to match the pill shell beside it — a default-height button
              stood a few pixels taller and the row read as two unrelated
              controls that happened to be adjacent. Outline, not the pill's
              solid fill: this one *does* something rather than selecting. */}
          <Button
            variant="outline"
            size="sm"
            className="h-7"
            disabled={syncing || loading}
            onClick={sync}
          >
            {syncing ? (
              <Loader2 className="size-3.5 animate-spin" />
            ) : (
              <RefreshCw className="size-3.5" />
            )}
            Sync
          </Button>
        </div>
      </div>

      {/* A five-second wait behind a spinning icon reads as a hung button. The
          bar and the counter are what separate "slow" from "stuck" — and the
          first load waits on the same sync, because the server syncs itself
          when it has nothing stored. */}
      {syncing || loading ? (
        <SyncProgress label={syncing ? "Fetching from Metricool" : "Loading competitor posts"} />
      ) : null}

      {error ? (
        <QueryError error={error} onRetry={refresh} />
      ) : loading || !data ? (
        // `!data` too — `loading` alone showed an empty grid while the Page
        // scope resolved. See `loading` in `use-query.ts` for the root of it.
        <CardGridLoading />
      ) : data.length === 0 ? (
        <EmptyGrid reach={reach} error={reachError} />
      ) : (
        <div className="grid gap-3 grid-cols-[repeat(auto-fill,minmax(360px,1fr))]">
          {data?.map((item) => (
            <SourceCard
              key={item.id}
              {...item}
              selected={cart.has(item)}
              onToggle={() => cart.toggle(item)}
            />
          ))}
        </div>
      )}
    </>
  );
}

/**
 * An empty grid, with the reason on it.
 *
 * Client feedback G2 (2026-08-16): *"NONE from chosen posts were generated."*
 * They were working on Pages that have **zero** competitors configured in
 * Metricool — six of the ten do — and this tab rendered an empty `<div>`, which
 * looks exactly like a quiet week. Nothing on screen said there was nothing to
 * choose from, so the reasonable conclusion was that generation was broken.
 *
 * The three causes need three different next moves, which is why they are told
 * apart rather than sharing one "no results" line:
 *
 * - nothing reaches this Page at all — **Sync cannot help**, competitors have to
 *   be added in Metricool and assigned on Settings;
 * - competitors are assigned but no post has arrived — Sync is exactly right;
 * - anything else, where saying less is better than guessing.
 *
 * The counts are local, so this cannot hang or 502 while explaining an outage.
 * See `get_competitor_reach`.
 */
function EmptyGrid({
  reach,
  error,
}: {
  reach: CompetitorReach | null;
  error: string | null;
}) {
  // No reason to give, but still an empty grid to account for. Saying only the
  // part we are sure of beats rendering nothing, which is the bug being fixed —
  // this branch is how it came back during verification, when the counts 404'd
  // against a stale server and the screen went blank again.
  if (error !== null) {
    return (
      <div className="rounded-lg border border-dashed p-8 text-center">
        <p className="text-sm font-medium">No competitor posts to show</p>
      </div>
    );
  }

  // Silence until the counts land, rather than a wrong reason for half a second.
  if (!reach) return null;

  // Nothing is assigned and nothing ever arrived under this Page's own name.
  const nothingReaches = reach.assigned === 0 && reach.own_set_posts === 0;

  // Assignments exist and are reading nothing, while this Page's own set holds
  // posts. Measured on Bible Focus, 2026-08-17: one assignment, zero visible
  // posts, **430 posts in its own set**. Not an empty week — a hidden pool.
  const hiddenByAssignment = reach.assigned > 0 && reach.own_set_posts > 0;

  return (
    <div className="rounded-lg border border-dashed p-8 text-center">
      <p className="text-sm font-medium">
        {nothingReaches
          ? "No competitors reach this Page yet"
          : hiddenByAssignment
            ? "This Page's assignments are reading nothing"
            : "Nothing has been synced for this Page"}
      </p>
      <p className="mx-auto mt-2 max-w-lg text-xs leading-relaxed text-muted-foreground">
        {nothingReaches ? (
          <>
            Nothing is assigned to it, and nothing has ever arrived through its own
            Metricool set — so <strong>Sync will not help</strong>. Add competitors
            under this Page in Metricool, then tick the ones it should read on{" "}
            <Link href="/settings" className="underline underline-offset-2">
              Settings
            </Link>
            . A competitor added under any Page can be read by all of them, which
            is what the 100-per-account ceiling forces.
          </>
        ) : hiddenByAssignment ? (
          <>
            {reach.assigned} competitor{reach.assigned === 1 ? " is" : "s are"}{" "}
            assigned to this Page and none of them has a stored post — while{" "}
            <strong>{reach.own_set_posts.toLocaleString()} posts</strong> sit in its
            own Metricool set, hidden. A Page reads its own set only until it has
            its first assignment; after that it reads exactly what is ticked. Fix
            it on{" "}
            <Link href="/settings" className="underline underline-offset-2">
              Settings
            </Link>{" "}
            — tick competitors that are actually posting, or untick them all to go
            back to reading the whole set.
          </>
        ) : (
          <>
            This Page reads its own Metricool set and none of those posts is stored
            yet. Sync pulls the last seven days.
          </>
        )}
      </p>
    </div>
  );
}

function RssTab() {
  const cart = useCart();
  const { pageId } = usePageScope();
  const { data, loading, error, refresh } = useQuery(() => getRss(pageId!), [pageId], {
    enabled: pageId !== null,
  });
  const [refreshing, setRefreshing] = useState(false);

  return (
    <>
      <div className="flex items-center justify-between gap-3 pb-3">
        <p className="text-xs text-muted-foreground">
          {/* Was "Seven curated feeds" — a number that was only ever true of
              History Retraced, and went stale the moment a Page with five was
              configured. The count is in `config/sources.yml`, not here. */}
          This Page&rsquo;s curated feeds, 7-day window. Nothing here exists in the
          database yet.
        </p>
        <Button
          variant="outline"
          size="sm"
          disabled={refreshing || loading}
          onClick={async () => {
            setRefreshing(true);
            await refresh();
            setRefreshing(false);
          }}
        >
          {refreshing ? (
            <Loader2 className="size-3.5 animate-spin" />
          ) : (
            <RefreshCw className="size-3.5" />
          )}
          Refresh
        </Button>
      </div>

      {/* Same wait, same bar as Competitors: seven feeds fetched live, and the
          slowest one sets the pace. `refresh()` leaves the old items up, so
          without this the screen looks untouched until they change. */}
      {refreshing || loading ? (
        <SyncProgress label={refreshing ? "Fetching feeds" : "Loading feeds"} />
      ) : null}

      {/* A feed that rots goes unnoticed unless its failure is on screen. */}
      {data?.failures.length ? (
        <div className="mb-3 flex flex-col gap-1 rounded-md border border-gold/40 bg-gold/[0.07] px-3 py-2 text-xs">
          <span className="flex items-center gap-1.5 font-medium">
            <AlertTriangle className="size-3.5" />
            {data.failures.length} feed did not answer
          </span>
          {data.failures.map((failure) => (
            <span key={failure.feed_url} className="truncate text-muted-foreground">
              {failure.feed_url} — {failure.error}
            </span>
          ))}
        </div>
      ) : null}

      {error ? (
        <QueryError error={error} onRetry={refresh} />
      ) : loading || !data ? (
        // `!data` for the same reason as the Competitors tab above.
        <CardGridLoading />
      ) : (
        <div className="grid gap-3 grid-cols-[repeat(auto-fill,minmax(360px,1fr))]">
          {data.items.map((item) => (
            <SourceCard
              key={item.external_id}
              {...item}
              selected={cart.has(item)}
              onToggle={() => cart.toggle(item)}
            />
          ))}
        </div>
      )}
    </>
  );
}

function TweetsTab() {
  const cart = useCart();
  const [url, setUrl] = useState("");
  const [looking, setLooking] = useState(false);
  const [found, setFound] = useState<LiveSourceItem[]>([]);

  async function lookup(event: React.FormEvent) {
    event.preventDefault();
    if (!url.trim()) return;
    setLooking(true);
    try {
      const tweet = await getTweet(url.trim());
      setFound((current) =>
        current.some((item) => item.external_id === tweet.external_id)
          ? current
          : [tweet, ...current],
      );
      setUrl("");
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "Lookup failed");
    } finally {
      setLooking(false);
    }
  }

  return (
    <>
      <form onSubmit={lookup} className="flex gap-2 pb-3">
        <Input
          value={url}
          onChange={(event) => setUrl(event.target.value)}
          placeholder="https://x.com/HistoryInPics/status/1817449230118928441"
          className="font-mono text-xs"
        />
        <Button type="submit" variant="outline" disabled={looking || !url.trim()}>
          {looking ? <Loader2 className="size-4 animate-spin" /> : <Search className="size-4" />}
          Look up
        </Button>
      </form>

      {found.length === 0 ? (
        <p className="rounded-lg border border-dashed p-10 text-center text-sm text-muted-foreground">
          Paste a tweet URL. There is no feed to browse — a tweet is one lookup at a time.
        </p>
      ) : (
        <div className="grid gap-3 grid-cols-[repeat(auto-fill,minmax(360px,1fr))]">
          {found.map((item) => (
            <SourceCard
              key={item.external_id}
              {...item}
              selected={cart.has(item)}
              onToggle={() => cart.toggle(item)}
            />
          ))}
        </div>
      )}
    </>
  );
}

/**
 * The bar, plus how long it has been going.
 *
 * Mounted only while a fetch is in flight, so the counter starts at zero for
 * each one without anything having to reset it.
 */
function SyncProgress({ label }: { label: string }) {
  const seconds = useElapsedSeconds();

  return (
    <div className="flex flex-col gap-1.5 pb-3">
      <Progress />
      <p className="text-xs text-muted-foreground">
        {label}…{seconds > 0 ? ` ${seconds}s` : ""}
      </p>
    </div>
  );
}

/** Whole seconds since mount. Ticks faster than it displays, so the number
    turns over on the second rather than up to a second late. */
function useElapsedSeconds() {
  const [seconds, setSeconds] = useState(0);

  useEffect(() => {
    const started = Date.now();
    const id = setInterval(() => setSeconds(Math.floor((Date.now() - started) / 1000)), 200);
    return () => clearInterval(id);
  }, []);

  return seconds;
}

/** Was a grid of six grey cards; a spinner says the same thing once. */
function CardGridLoading() {
  return <Loading label="Loading sources" className="h-64" />;
}
