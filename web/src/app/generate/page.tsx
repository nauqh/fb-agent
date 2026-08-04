"use client";

import { useRouter } from "next/navigation";
import Link from "next/link";
import { useState } from "react";
import { AlertTriangle, ArrowRight, Loader2, Sparkles, X } from "lucide-react";
import { toast } from "sonner";

import { ScreenHeader } from "@/components/screen";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { generate } from "@/lib/api/drafts";
import { getQuotaUsage, listPages } from "@/lib/api/pages";
import { sourceKey, useCart } from "@/lib/cart";
import { isFactual } from "@/lib/types";
import { useQuery } from "@/lib/use-query";
import { cn } from "@/lib/utils";

/**
 * The staging screen for a run.
 *
 * It exists because a run has two things worth seeing before it starts: how
 * many Drafts it will produce, and whether the Page is already at its Quota for
 * today. Both were previously buried in a page-picker dialog.
 */
export default function GenerateScreen() {
  const cart = useCart();
  const router = useRouter();
  const [topic, setTopic] = useState("");
  const [running, setRunning] = useState(false);

  const { data: pages } = useQuery(() => listPages(), []);

  const page = pages?.[0];
  const { data: used } = useQuery(
    () => getQuotaUsage(page!.id),
    [page?.id],
    { enabled: Boolean(page) },
  );

  const usingTopic = cart.count === 0;
  const draftCount = usingTopic ? (topic.trim() ? 1 : 0) : cart.count;
  const atQuota = page !== undefined && used !== null && used !== undefined && used >= page.daily_quota;

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
      toast.success(
        `${ids.length} draft${ids.length === 1 ? "" : "s"} generating.`,
        { description: "Progress is on the Review screen." },
      );
      router.push(`/review/${ids[0]}`);
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "Generate failed");
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="w-full max-w-4xl lg:min-h-0 lg:flex-1 lg:overflow-y-auto">
      <ScreenHeader
        title="Generate"
        hint="One Draft per Source Item, per Page. v1 has one Page, so the count is the Cart."
      />

      <div className="space-y-6">
        <section className="rounded-lg border">
          <div className="flex items-center justify-between border-b px-4 py-3">
            <h2 className="text-sm font-medium">
              Cart{cart.count > 0 ? <span className="text-muted-foreground"> · {cart.count}</span> : null}
            </h2>
            <Button variant="ghost" size="sm" className="-mr-2 h-7" asChild>
              <Link href="/sources">Add more</Link>
            </Button>
          </div>

          {cart.count === 0 ? (
            <div className="space-y-4 px-4 py-5">
              <p className="text-sm text-muted-foreground">
                The Cart is empty. Pick Source Items on{" "}
                <Link href="/sources" className="underline underline-offset-2">
                  Sources
                </Link>
                , or write from a topic instead.
              </p>
              <div className="space-y-2">
                <Label htmlFor="topic">Topic</Label>
                <Input
                  id="topic"
                  value={topic}
                  onChange={(event) => setTopic(event.target.value)}
                  placeholder="The Great Molasses Flood, Boston 1919"
                />
                <p className="text-xs text-muted-foreground">
                  A topic-only Draft has no Source Item — nothing binds the story except the
                  topic itself.
                </p>
              </div>
            </div>
          ) : (
            <ul className="divide-y">
              {cart.items.map((item) => (
                <li key={sourceKey(item)} className="flex items-start gap-3 px-4 py-3">
                  <div className="min-w-0 flex-1">
                    <p className="flex items-center gap-2 text-sm font-medium">
                      {item.author}
                      <span
                        className={cn(
                          "rounded px-1.5 py-0.5 text-[10px] font-normal uppercase tracking-wide",
                          isFactual(item.kind)
                            ? "bg-foreground/10 text-foreground/70"
                            : "bg-muted text-muted-foreground",
                        )}
                      >
                        {isFactual(item.kind) ? "binds the story" : "style only"}
                      </span>
                    </p>
                    <p className="line-clamp-2 pt-0.5 text-sm text-muted-foreground">
                      {item.text}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => cart.remove(item)}
                    className="rounded p-1 text-muted-foreground hover:text-foreground"
                    aria-label="Remove from cart"
                  >
                    <X className="size-4" />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="rounded-lg border">
          <div className="border-b px-4 py-3">
            <h2 className="text-sm font-medium">Target Page</h2>
          </div>
          <div className="px-4 py-4">
            {page ? (
              <div className="flex items-center justify-between gap-4">
                <div>
                  <p className="text-sm font-medium">{page.name}</p>
                  <p className="pt-0.5 font-mono text-xs text-muted-foreground">
                    {page.facebook_page_id}
                  </p>
                </div>
                <div className="text-right">
                  <p
                    className={cn(
                      "text-sm tabular-nums",
                      atQuota ? "text-gold-foreground" : "text-muted-foreground",
                    )}
                  >
                    {used ?? 0} / {page.daily_quota} approved today
                  </p>
                  {atQuota ? (
                    <p className="flex items-center justify-end gap-1 pt-0.5 text-xs text-muted-foreground">
                      <AlertTriangle className="size-3" />
                      At quota — this will not stop the run
                    </p>
                  ) : null}
                </div>
              </div>
            ) : null}
          </div>
        </section>

        <Separator />

        <div className="flex items-center justify-between gap-4 pb-10">
          <p className="text-sm text-muted-foreground tabular-nums">
            {usingTopic ? (
              <>1 topic × 1 page = {draftCount} draft</>
            ) : (
              <>
                {cart.count} source{cart.count === 1 ? "" : "s"} × 1 page ={" "}
                <span className="text-foreground">{draftCount} drafts</span>
              </>
            )}
          </p>
          <Button
            size="lg"
            className="bg-gold text-gold-foreground hover:bg-gold/90"
            disabled={draftCount === 0 || running}
            onClick={run}
          >
            {running ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <Sparkles className="size-4" />
            )}
            Generate
            <ArrowRight className="size-4" />
          </Button>
        </div>
      </div>
    </div>
  );
}
