"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, Check, Filter, Loader2, RefreshCw, Search } from "lucide-react";
import { toast } from "sonner";

import { CartPanel } from "@/components/cart-panel";
import { ScreenHeader } from "@/components/screen";
import { QueryError } from "@/components/query-error";
import { SourceCard } from "@/components/source-card";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { getRss, getCompetitorPosts, getTweet } from "@/lib/api/sources";
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

/**
 * Which Pages' competitors to draw from. Empty means every Page.
 *
 * Competitor posts are a shared pool, unlike the feeds: Metricool caps an
 * account at 100 competitors *in total*, so five Pages that should each watch
 * the same twenty sources cannot each be given them. A source is configured
 * under whichever Page had room and assigned to the Pages that read it.
 *
 * The default is the selected Page — that is the work in front of you — and
 * widening is one click, because the pool is the point.
 */
function ScopeFilter({
  scope,
  onChange,
}: {
  scope: number[];
  onChange: (next: number[]) => void;
}) {
  const { pages } = usePageScope();
  if (pages.length < 2) return null;

  const label =
    scope.length === 0
      ? "All pages"
      : scope.length === 1
        ? (pages.find((page) => page.id === scope[0])?.name ?? "1 page")
        : `${scope.length} pages`;

  function toggle(id: number) {
    onChange(scope.includes(id) ? scope.filter((one) => one !== id) : [...scope, id]);
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="sm" className="h-8">
          <Filter className="size-3.5" />
          {label}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-52">
        <DropdownMenuItem onSelect={() => onChange([])}>
          <span className="flex-1">All pages</span>
          {/* The tick holds its slot either way, so the rows do not shift. */}
          <Check className={scope.length === 0 ? "size-3.5" : "size-3.5 opacity-0"} />
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        {pages.map((page) => (
          <DropdownMenuItem
            key={page.id}
            // Kept open: picking a scope is usually several ticks, and closing
            // on the first one makes the multi-select feel broken.
            onSelect={(event) => {
              event.preventDefault();
              toggle(page.id);
            }}
          >
            <span className="flex-1 truncate">{page.name}</span>
            <Check
              className={scope.includes(page.id) ? "size-3.5" : "size-3.5 opacity-0"}
            />
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function CompetitorsTab() {
  const cart = useCart();
  const { pageId } = usePageScope();
  // `null` means "not chosen yet", which resolves to the selected Page. Held
  // separately rather than initialised in an effect: an effect that seeds state
  // renders once with the wrong value first, and this repo's lint rule against
  // set-state-in-effect exists for exactly that.
  const [chosen, setChosen] = useState<number[] | null>(null);
  const scope = chosen ?? (pageId !== null ? [pageId] : []);
  const scopeKey = scope.join(",");

  // `pageId` gates the query: null means the Pages have not landed yet, and
  // firing against a guessed id would show the wrong Page's competitors for a
  // beat before correcting itself.
  const { data, loading, error, refresh } = useQuery(
    () => getCompetitorPosts(scope),
    [scopeKey, pageId],
    { enabled: pageId !== null },
  );
  const [syncing, setSyncing] = useState(false);

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
      await getCompetitorPosts(scope, true);
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
        <div className="flex min-w-0 items-center gap-2">
          <ScopeFilter scope={scope} onChange={setChosen} />
          <p className="truncate text-xs text-muted-foreground">
            Synced from Metricool, newest first. A source is shared across pages —
            assign them on Settings.
          </p>
        </div>
        <Button variant="outline" size="sm" disabled={syncing || loading} onClick={sync}>
          {syncing ? (
            <Loader2 className="size-3.5 animate-spin" />
          ) : (
            <RefreshCw className="size-3.5" />
          )}
          Sync
        </Button>
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
      ) : loading ? (
        <CardGridSkeleton />
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
      ) : loading ? (
        <CardGridSkeleton />
      ) : (
        <div className="grid gap-3 grid-cols-[repeat(auto-fill,minmax(360px,1fr))]">
          {data?.items.map((item) => (
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

function CardGridSkeleton() {
  return (
    <div className="grid gap-3 grid-cols-[repeat(auto-fill,minmax(360px,1fr))]">
      {Array.from({ length: 6 }).map((_, index) => (
        <Skeleton key={index} className="h-44 rounded-lg" />
      ))}
    </div>
  );
}
