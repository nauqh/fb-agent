"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, Loader2, RefreshCw, Search } from "lucide-react";
import { toast } from "sonner";

import { CartPanel } from "@/components/cart-panel";
import { ScreenHeader } from "@/components/screen";
import { QueryError } from "@/components/query-error";
import { SourceCard } from "@/components/source-card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { getRss, getCompetitorPosts, getTweet } from "@/lib/api/sources";
import type { LiveSourceItem } from "@/lib/fixtures/sources";
import { useCart } from "@/lib/cart";
import { emit } from "@/lib/store";
import { useQuery } from "@/lib/use-query";

/** The Page every competitor set belongs to. One Page in v1, so it is a constant. */
const PAGE_ID = 1;

export default function SourcesScreen() {
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <ScreenHeader title="Sources" />

      <Tabs
        defaultValue="competitors"
        className="grid min-h-0 flex-1 gap-6 lg:grid-cols-[minmax(0,1fr)_320px]"
      >
        <div className="flex min-h-0 flex-col gap-4">
          {/* `*:` reaches the triggers, so the width and padding live in one
              place instead of being repeated on each of the three. */}
          <TabsList className="shrink-0 gap-1.5 p-1 *:min-w-28 *:px-4">
            <TabsTrigger value="competitors">Competitors</TabsTrigger>
            <TabsTrigger value="tweets">Tweets</TabsTrigger>
            <TabsTrigger value="rss">RSS</TabsTrigger>
          </TabsList>

          <TabsContent value="competitors" className="min-h-0 flex-1 overflow-y-auto">
            <CompetitorsTab />
          </TabsContent>
          <TabsContent value="tweets" className="min-h-0 flex-1 overflow-y-auto">
            <TweetsTab />
          </TabsContent>
          <TabsContent value="rss" className="min-h-0 flex-1 overflow-y-auto">
            <RssTab />
          </TabsContent>
        </div>

        {/* The Cart is a full-height column now that the shell is bounded —
            no viewport arithmetic to keep in sync with the header. */}
        <div className="min-h-0 lg:h-full">
          <CartPanel />
        </div>
      </Tabs>
    </div>
  );
}

function CompetitorsTab() {
  const cart = useCart();
  const { data, loading, error, refresh } = useQuery(() => getCompetitorPosts(PAGE_ID), []);
  const [syncing, setSyncing] = useState(false);

  /**
   * Syncing is the operator's call, not the tab's.
   *
   * Opening the tab used to cost ~5.5s and 1.6MB to pull 500 posts and show 60,
   * against a seven-day window that gains about three an hour. The server syncs
   * on its own only when it has nothing stored.
   */
  async function sync() {
    setSyncing(true);
    try {
      await getCompetitorPosts(PAGE_ID, true);
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
          Synced from Metricool, newest first. Which pages are Competitors is configured in
          Metricool — never here.
        </p>
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
        <div className="grid gap-3 sm:grid-cols-2 2xl:grid-cols-3">
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
  const { data, loading, error, refresh } = useQuery(() => getRss(PAGE_ID), []);
  const [refreshing, setRefreshing] = useState(false);

  return (
    <>
      <div className="flex items-center justify-between gap-3 pb-3">
        <p className="text-xs text-muted-foreground">
          Seven curated feeds, 7-day window. Nothing here exists in the database yet.
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
        <div className="grid gap-3 sm:grid-cols-2 2xl:grid-cols-3">
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
        <div className="grid gap-3 sm:grid-cols-2 2xl:grid-cols-3">
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
    <div className="grid gap-3 sm:grid-cols-2 2xl:grid-cols-3">
      {Array.from({ length: 6 }).map((_, index) => (
        <Skeleton key={index} className="h-44 rounded-lg" />
      ))}
    </div>
  );
}
