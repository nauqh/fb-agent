"use client";

import { useState } from "react";
import {
  Check,
  ExternalLink,
  Loader2,
  Plus,
  Rss,
  Trash2,
} from "lucide-react";
import { toast } from "sonner";

import { CompetitorMark } from "@/components/competitor-mark";
import { Card, Counts } from "@/components/config-card";
import { ScreenHeader } from "@/components/screen";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { getCompetitorPages, getSourcesConfig } from "@/lib/api/sources";
import { setAssignments } from "@/lib/api/competitors";
import { addFeed, removeFeed } from "@/lib/api/feeds";
import { usePageScope } from "@/lib/page-scope";
import { emit } from "@/lib/store";
import { useQuery } from "@/lib/use-query";
import { cn } from "@/lib/utils";

/**
 * One Page, and nothing to type into.
 *
 * Read-only throughout, which is the honest shape rather than a missing
 * feature. Identity comes from Metricool. Layout is `layout.yml`. The prompts
 * are files precisely so they are reviewed in git rather than typed into a box,
 * and a textarea here would quietly undo that. What is left is a window onto
 * what the run is actually configured with — and every piece of it is edited
 * somewhere a diff can be read.
 */
export default function SettingsScreen() {
  const { page, pageId } = usePageScope();

  const { data: sources } = useQuery(() => getSourcesConfig(pageId!), [pageId], {
    enabled: pageId !== null,
  });
  // Its own query, and its own error: this is the only thing on the screen that
  // leaves the building, so a Metricool outage must degrade to one message in
  // one section rather than an empty Settings screen.
  const {
    data: competitors,
    error: competitorsError,
    loading: competitorsLoading,
  } = useQuery(() => getCompetitorPages(), []);


  /**
   * Assign or unassign this competitor for the Page in the switcher.
   *
   * Sends the whole set, because the endpoint replaces rather than merges — a
   * tick list is a set, and sending it whole makes two fast clicks land on the
   * state the second one described.
   *
   * The first assignment on a Page is a real change of behaviour: until then
   * the Page reads whatever competitor set it owns in Metricool, and afterwards
   * it reads only what is assigned. The hint under the card says so, because
   * nothing else on screen would.
   */
  async function toggleAssignment(providerId: string) {
    if (pageId === null || !competitors) return;

    const current = competitors
      .filter((one) => one.assigned_page_ids.includes(pageId))
      .map((one) => one.provider_id);
    const next = current.includes(providerId)
      ? current.filter((one) => one !== providerId)
      : [...current, providerId];

    try {
      await setAssignments(
        pageId,
        next,
        Object.fromEntries(competitors.map((one) => [one.provider_id, one.name])),
      );
      emit();
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "Could not save");
    }
  }

  if (!page) {
    return (
      <div className="w-full space-y-4">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-40" />
      </div>
    );
  }

  return (
    // `lg:pr-3` — only where this element is the scroller. Below `lg` the page
    // scrolls instead and the padding would just be a stray inset.
    //
    // No `max-w-3xl` any more. That width was right when the screen was four
    // stacked sections under one Page; with Feeds and Competitors on it the
    // column ran off the bottom while 40% of a 1400px viewport sat empty.
    //
    // Identity and Feeds are a pair now: both short, both about this Page, and
    // stacked they left a column of white beside them. Composed Image and the
    // prompts left for Global, which is where account-wide things live
    // beside it. The shell's own `max-w-[1600px]` is the bound now.
    <div className="w-full pb-16 lg:min-h-0 lg:flex-1 lg:overflow-y-auto lg:pr-3">
      <ScreenHeader title="Settings" />

      {/* `items-start` so a short card does not stretch to its row's height —
          Prompts beside Composed Image should keep their own sizes rather than
          both becoming as tall as the taller. */}
      <div className="grid items-start gap-4 xl:grid-cols-2">
        <Card
          title={page.name}
          hint="Identity comes from Metricool and is not editable here."
        >
          <p className="font-mono text-xs text-muted-foreground">
            facebook {page.facebook_page_id}
            <span className="mx-2">·</span>
            metricool {page.metricool_blog_id}
          </p>

          <div className="space-y-2 pt-4">
            <Label>Watermark</Label>
            {page.watermark_image_path ? (
              <div className="flex items-center gap-3">
                {/* On black, because that is the only background it is ever
                    drawn against and it is white ink. */}
                <span className="rounded-md bg-black px-3 py-2">
                  {/* eslint-disable-next-line @next/next/no-img-element -- a
                      committed asset at its natural ratio, not a content image. */}
                  <img
                    src={`/api/${page.watermark_image_path}`}
                    alt={`${page.name} watermark`}
                    className="h-10 w-auto"
                  />
                </span>
                <code className="min-w-0 truncate text-xs text-muted-foreground">
                  {page.watermark_image_path}
                </code>
              </div>
            ) : (
              <p className="text-sm text-destructive">
                missing — nothing to composite over
              </p>
            )}
          </div>
        </Card>



        <Card
          title="Feeds"
          hint={
            <>
              This Page&rsquo;s feeds. Adding one probes it first &mdash; a feed
              that does not answer is not saved.
            </>
          }
          meta={
            sources ? (
              <Counts>
                {sources.feeds.length} feeds · {sources.since_days}d window ·{" "}
                {sources.max_items} shown
              </Counts>
            ) : null
          }
        >
          {sources ? (
            <div className="divide-y rounded-lg border">
              <AddFeed pageId={pageId} />
              {sources.feeds.map((feed) => (
                // The row opens the feed itself. Checking a feed means looking
                // at what it is serving right now, and this screen is where you
                // are when you doubt one.
                <div
                  key={feed.url}
                  className="group flex items-center gap-3 px-3 py-2 text-xs hover:bg-muted/50"
                >
                  <a
                    href={feed.url}
                    target="_blank"
                    rel="noreferrer"
                    className="flex min-w-0 flex-1 items-center gap-3"
                    title={feed.note ?? undefined}
                  >
                  <Rss className="size-3.5 shrink-0 text-muted-foreground" />
                  <span className="w-32 shrink-0 truncate font-medium">
                    {feed.name}
                  </span>
                  {/* The URL is what you would actually check, so it is shown
                      whole and allowed to truncate rather than reduced to a
                      hostname that proves nothing. */}
                  <code className="min-w-0 truncate text-muted-foreground">
                    {feed.url}
                  </code>
                  <ExternalLink className="size-3 shrink-0 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" />
                  </a>
                  <RemoveFeed id={feed.id} name={feed.name} />
                </div>
              ))}
            </div>
          ) : (
            <Skeleton className="h-40 rounded-lg" />
          )}
        </Card>

        {/* Full width: at 26 rows this is the longest thing on the screen, and
            in a half-width column it sets the page's height on its own. */}
        <Card
          className="xl:col-span-2"
          title="Competitors this Page reads"
          hint={
            <>
              Which of the pool this Page reads. Tick to assign; the same source
              can feed several Pages. The pool itself is on Global.
            </>
          }
          meta={
            competitors ? (
              <Counts>
                {competitors.length} configured
                {(() => {
                  const silent = competitors.filter(
                    (one) => one.posts_stored === 0,
                  ).length;
                  return silent ? (
                    <span className="text-destructive"> · {silent} silent</span>
                  ) : null;
                })()}
              </Counts>
            ) : null
          }
        >
          {competitorsError ? (
            // This section fails alone. Everything else on the screen is a
            // local file and cannot.
            <p className="rounded-lg border border-dashed p-4 text-xs text-destructive">
              {competitorsError}
            </p>
          ) : competitorsLoading || !competitors ? (
            <Skeleton className="h-40 rounded-lg" />
          ) : (
            // A grid, not one long list: twenty-six full-width rows is a
            // scroll, and the row has three short fields in it. Silent ones
            // come first from the server, so reading order still puts the
            // finding at the top left.
            <div className="grid gap-2 sm:grid-cols-2 2xl:grid-cols-3">
              {competitors.map((competitor) => (
                // `provider_id` is the Facebook page id, which is all
                // facebook.com needs — no screen name to go stale. A silent
                // competitor is the row you most want to open: it answers
                // whether the page died or merely went quiet.
                <div
                  key={competitor.provider_id}
                  className={cn(
                    "group flex items-center gap-2.5 rounded-lg border px-3 py-2 text-xs transition-colors hover:bg-muted/50",
                    competitor.posts_stored === 0 && "border-destructive/40",
                  )}
                >
                  {/* The row used to be one big <a>. It cannot be now: a toggle
                      nested in a link navigates on click, and the assignment is
                      the thing this row is here to change. The name keeps the
                      link — opening a silent competitor is how you tell a dead
                      page from a quiet one. */}
                  <a
                    href={`https://www.facebook.com/${competitor.provider_id}`}
                    target="_blank"
                    rel="noreferrer"
                    className="flex min-w-0 flex-1 items-center gap-2.5"
                  >
                  <CompetitorMark
                    name={competitor.name}
                    picture={competitor.picture}
                  />
                  <div className="min-w-0 flex-1">
                    <p className="flex items-center gap-1.5 truncate font-medium">
                      <span className="truncate">{competitor.name}</span>
                      <ExternalLink className="size-3 shrink-0 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" />
                    </p>
                    <p className="tabular-nums text-muted-foreground">
                      {(competitor.followers ?? 0).toLocaleString()} followers
                    </p>
                  </div>
                  <span
                    className={cn(
                      "shrink-0 text-right tabular-nums",
                      competitor.posts_stored === 0
                        ? "text-destructive"
                        : "text-muted-foreground",
                    )}
                  >
                    {competitor.posts_stored === 0
                      ? "no posts"
                      : `${competitor.posts_stored} post${competitor.posts_stored === 1 ? "" : "s"}`}
                    </span>
                  </a>

                  <AssignToggle
                    assigned={
                      pageId !== null &&
                      competitor.assigned_page_ids.includes(pageId)
                    }
                    pageName={page.name}
                    otherPages={competitor.assigned_page_ids.length}
                    onToggle={() => toggleAssignment(competitor.provider_id)}
                  />
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}

/**
 * One titled block. Was a `<div>` plus a `<Separator>` repeated five times down
 * a single column; as cards in a grid the screen uses the width the shell
 * gives it, and a section can be moved without dragging a separator with it.
 */


/** The numbers that describe a section, beside its title rather than under it. */








/**
 * Whether this Page reads this competitor.
 *
 * A button rather than a checkbox because it is the only control in the row and
 * it says what it does. `otherPages` is shown when another Page reads a
 * competitor this one does not — that is the shared pool being visible, and
 * without it the row looks unused when it is not.
 */
function AssignToggle({
  assigned,
  pageName,
  otherPages,
  onToggle,
}: {
  assigned: boolean;
  pageName: string;
  otherPages: number;
  onToggle: () => void;
}) {
  const alsoElsewhere = otherPages - (assigned ? 1 : 0);

  return (
    <button
      type="button"
      onClick={onToggle}
      title={
        assigned
          ? `${pageName} reads this competitor. Click to stop.`
          : `Let ${pageName} read this competitor.`
      }
      className={cn(
        "flex shrink-0 items-center gap-1 rounded-md border px-2 py-1 text-[11px] transition-colors",
        assigned
          ? "border-primary/40 bg-primary/10 text-primary"
          : "text-muted-foreground hover:bg-muted",
      )}
    >
      {assigned ? <Check className="size-3" /> : <Plus className="size-3" />}
      {assigned ? "Reading" : "Assign"}
      {alsoElsewhere > 0 ? (
        <span className="text-muted-foreground">+{alsoElsewhere}</span>
      ) : null}
    </button>
  );
}


/**
 * Add a feed. The server probes it before it will write the row.
 *
 * The probe is not decoration. The feed list used to live in
 * `config/sources.yml`, curated "because every candidate has to be probed
 * before it earns a place, which is not a thing to do from a form" — so the
 * probing moved into the form rather than being dropped, and its measurements
 * come back in the toast. A feed that does not answer, does not parse, or
 * parses to nothing is refused with a message written to be read here.
 */
function AddFeed({ pageId }: { pageId: number | null }) {
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [saving, setSaving] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (pageId === null || !name.trim() || !url.trim()) return;

    setSaving(true);
    try {
      const { probe } = await addFeed({
        page_id: pageId,
        name: name.trim(),
        url: url.trim(),
      });
      // The numbers that decided whether a feed earned its place, shown at the
      // moment the decision is made rather than stored and shown stale later.
      toast.success(
        probe
          ? `${name.trim()} added — ${probe.items} items, ${probe.with_images} imaged, ${probe.median_summary}-char summaries`
          : `${name.trim()} added`,
      );
      setName("");
      setUrl("");
      emit();
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "Could not add that feed");
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={submit} className="flex items-center gap-2 bg-muted/30 px-3 py-2">
      <Plus className="size-3.5 shrink-0 text-muted-foreground" />
      <Input
        value={name}
        onChange={(event) => setName(event.target.value)}
        placeholder="Publisher"
        aria-label="Publisher name"
        className="h-7 w-32 shrink-0 text-xs"
      />
      <Input
        value={url}
        onChange={(event) => setUrl(event.target.value)}
        placeholder="https://example.com/feed"
        aria-label="Feed URL"
        className="h-7 min-w-0 flex-1 text-xs"
      />
      <Button
        type="submit"
        size="sm"
        variant="outline"
        className="h-7 shrink-0"
        disabled={saving || pageId === null || !name.trim() || !url.trim()}
      >
        {saving ? <Loader2 className="size-3 animate-spin" /> : "Probe & add"}
      </Button>
    </form>
  );
}

/** Removing a feed changes tomorrow’s grid and nothing already published:
 *  no row points at a feed, so this cannot cascade into past work. */
function RemoveFeed({ id, name }: { id: number; name: string }) {
  const [busy, setBusy] = useState(false);

  async function remove() {
    setBusy(true);
    try {
      await removeFeed(id);
      toast.success(`${name} removed`);
      emit();
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "Could not remove");
    } finally {
      setBusy(false);
    }
  }

  return (
    <button
      type="button"
      onClick={remove}
      disabled={busy}
      aria-label={`Remove ${name}`}
      title={`Remove ${name}`}
      className="shrink-0 rounded p-1 text-muted-foreground opacity-0 transition-opacity hover:bg-destructive/10 hover:text-destructive group-hover:opacity-100 focus-visible:opacity-100"
    >
      {busy ? <Loader2 className="size-3 animate-spin" /> : <Trash2 className="size-3" />}
    </button>
  );
}



