"use client";

import { useCallback, useState } from "react";
import { AlertTriangle, Loader2, RefreshCw, Search } from "lucide-react";
import { toast } from "sonner";

import { CartPanel } from "@/components/cart-panel";
import { ScreenHeader } from "@/components/screen";
import { SourceCard } from "@/components/source-card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { getArticles, getRivals, getTweet, saveSources } from "@/lib/api/sources";
import type { LiveSourceItem } from "@/lib/fixtures/sources";
import { useCart } from "@/lib/cart";
import { useQuery } from "@/lib/use-query";

/** The Page every rival set belongs to. One Page in v1, so it is a constant. */
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
        // Already a row. Untick drops it from the Cart only — the row stays,
        // because a Draft generated from it points back at it.
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
        hint="Rival posts are synced and already rows. Tweets and articles are live — ticking one is what writes it."
      />

      <Tabs
        defaultValue="rivals"
        className="grid min-h-0 flex-1 gap-6 lg:grid-cols-[minmax(0,1fr)_320px]"
      >
        <div className="flex min-h-0 flex-col gap-4">
          <TabsList className="shrink-0">
            <TabsTrigger value="rivals">Rivals</TabsTrigger>
            <TabsTrigger value="tweets">Tweets</TabsTrigger>
            <TabsTrigger value="articles">Articles</TabsTrigger>
          </TabsList>

          <TabsContent value="rivals" className="min-h-0 flex-1 overflow-y-auto">
            <RivalsTab />
          </TabsContent>
          <TabsContent value="tweets" className="min-h-0 flex-1 overflow-y-auto">
            <TweetsTab onTick={tick} savedIds={savedIds} pending={pending} />
          </TabsContent>
          <TabsContent value="articles" className="min-h-0 flex-1 overflow-y-auto">
            <ArticlesTab onTick={tick} savedIds={savedIds} pending={pending} />
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

function RivalsTab() {
  const cart = useCart();
  const { data, loading } = useQuery(() => getRivals(PAGE_ID), []);

  if (loading) return <CardGridSkeleton />;

  return (
    <>
      <p className="pb-3 text-xs text-muted-foreground">
        Synced from Metricool, newest window, sorted by reactions. Which pages are Rivals is
        configured in Metricool — never here.
      </p>
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
    </>
  );
}

interface LiveTabProps {
  onTick: (item: LiveSourceItem) => void;
  savedIds: Record<string, number>;
  pending: string[];
}

function ArticlesTab({ onTick, savedIds, pending }: LiveTabProps) {
  const cart = useCart();
  const { data, loading, refresh } = useQuery(() => getArticles(), []);
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

      {loading ? (
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
