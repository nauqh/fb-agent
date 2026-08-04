"use client";

import { useCallback, useState } from "react";
import { AlertTriangle, Loader2, RefreshCw, Search } from "lucide-react";
import { toast } from "sonner";

import { CartPanel } from "@/components/cart-panel";
import { ScreenHeader } from "@/components/screen";
import { QueryError } from "@/components/query-error";
import { SourceCard } from "@/components/source-card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { getRss, getCompetitorPosts, getTweet, saveSources } from "@/lib/api/sources";
import type { LiveSourceItem } from "@/lib/fixtures/sources";
import { useCart } from "@/lib/cart";
import { emit } from "@/lib/store";
import { useQuery } from "@/lib/use-query";

/** The Page every competitor set belongs to. One Page in v1, so it is a constant. */
const PAGE_ID = 1;

export default function SourcesScreen() {
  const cart = useCart();

  /**
   * `external_id` → row id, for items that were live until they were ticked.
   *
   * The grid knows external ids; the Cart holds row ids. Ticking is what
   * creates the row, so this map is the bridge between the two — and it is why
   * a tick is a round trip rather than a local toggle.
   */
  const [savedIds, setSavedIds] = useState<Record<string, number>>({});
  const [pending, setPending] = useState<string[]>([]);

  const tick = useCallback(
    async (item: LiveSourceItem) => {
      const known = savedIds[item.external_id];
      if (known !== undefined) {
        // Untick drops the id from the Cart; the row stays, and if nothing was
        // ever generated from it the row is an orphan. There is no DELETE, so
        // this leaks — tick ten, untick nine, generate one, and nine rows
        // remain referenced by nothing.
        //
        // Known and accepted until Phase 3, which moves the write to
        // POST /generate and removes this whole path along with `savedIds`.
        // See docs/plan.md, "Ticking stops writing". Not worth a DELETE route
        // that would be deleted again a week later.
        if (cart.has(known)) cart.remove(known);
        else cart.add(known);
        return;
      }

      setPending((current) => [...current, item.external_id]);
      try {
        const [saved] = await saveSources([item]);
        setSavedIds((current) => ({ ...current, [item.external_id]: saved.id }));
        cart.add(saved.id);
      } catch (cause) {
        toast.error(cause instanceof Error ? cause.message : "Could not save that item");
      } finally {
        setPending((current) => current.filter((id) => id !== item.external_id));
      }
    },
    [cart, savedIds],
  );

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <ScreenHeader
        title="Sources"
        hint="Competitor posts are synced and already rows. Tweets and RSS items are live — ticking one is what writes it."
      />

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
            <TweetsTab onTick={tick} savedIds={savedIds} pending={pending} />
          </TabsContent>
          <TabsContent value="rss" className="min-h-0 flex-1 overflow-y-auto">
            <RssTab onTick={tick} savedIds={savedIds} pending={pending} />
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
          Synced from Metricool, sorted by reactions. Which pages are Competitors is configured in
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
              selected={cart.has(item.id)}
              onToggle={() => (cart.has(item.id) ? cart.remove(item.id) : cart.add(item.id))}
            />
          ))}
        </div>
      )}
    </>
  );
}

interface LiveTabProps {
  onTick: (item: LiveSourceItem) => void;
  savedIds: Record<string, number>;
  pending: string[];
}

function RssTab({ onTick, savedIds, pending }: LiveTabProps) {
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
          {data?.items.map((item) => {
            const rowId = savedIds[item.external_id];
            return (
              <SourceCard
                key={item.external_id}
                {...item}
                selected={rowId !== undefined && cart.has(rowId)}
                pending={pending.includes(item.external_id)}
                onToggle={() => onTick(item)}
              />
            );
          })}
        </div>
      )}
    </>
  );
}

function TweetsTab({ onTick, savedIds, pending }: LiveTabProps) {
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
          {found.map((item) => {
            const rowId = savedIds[item.external_id];
            return (
              <SourceCard
                key={item.external_id}
                {...item}
                selected={rowId !== undefined && cart.has(rowId)}
                pending={pending.includes(item.external_id)}
                onToggle={() => onTick(item)}
              />
            );
          })}
        </div>
      )}
    </>
  );
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
