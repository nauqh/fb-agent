"use client";

import { useState } from "react";
import {
  Check,
  ExternalLink,
  Loader2,
  Plus,
  Clock,
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
import { Textarea } from "@/components/ui/textarea";
import { getCompetitorPages, getSourcesConfig } from "@/lib/api/sources";
import { setAssignments } from "@/lib/api/competitors";
import { addFeed, removeFeed } from "@/lib/api/feeds";
import {
  addSlot,
  listPromptFiles,
  listSlots,
  removeSlot,
  setPromptFile,
  updatePage,
} from "@/lib/api/pages";
import type { Page, PromptFile } from "@/lib/types";
import { usePageScope } from "@/lib/page-scope";
import { emit } from "@/lib/store";
import { useQuery } from "@/lib/use-query";
import { cn } from "@/lib/utils";

/**
 * One Page: what it is, and how it writes.
 *
 * Read-only throughout until 2026-08-17, and the reasoning held for what it was
 * aimed at — identity comes from Metricool, layout is `layout.yml`, and the
 * prompts are files so they are reviewed in git rather than typed into a box.
 *
 * Two things are editable now, and both are per-Page overrides that inherit
 * when empty rather than copies of a shared default:
 *
 * - **the lengths** (C6, C7), because the client asked for a 30-word hook and a
 *   1,500-character first comment on two Pages and not on the others;
 * - **the prompts** (F5), because they have been asking since 2026-08-15 and
 *   believed for six weeks that they had already written them. A file cannot
 *   answer that: Railway's filesystem is ephemeral, so an edit written to
 *   `api/prompts/pages/<slug>/` would be gone on the next redeploy.
 *
 * The globals stay files and stay uneditable here. Every Page reads them, and
 * a textarea on a shared default is what the drift was.
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

        <Card
          title="Publishing times"
          hint={
            <>
              The slots &ldquo;Schedule next available&rdquo; walks through. The
              same times every day, in this Page&rsquo;s zone (GMT+7).
            </>
          }
        >
          <TimeSlots pageId={pageId} />
        </Card>

        <Card
          title="How this Page writes"
          hint={
            <>
              Leave a box empty to use the house number. These are the lengths
              the writer is told to hit <em>and</em> the ones a draft is checked
              against &mdash; they cannot disagree.
            </>
          }
        >
          <WritingLimits page={page} />
        </Card>

        {/* Full width: three prompts of a few thousand characters each. */}
        <Card
          className="xl:col-span-2"
          title="Prompts"
          hint={
            <>
              What this Page tells the model. Empty means it inherits the
              reviewed default in <code>api/prompts/</code> &mdash; saving text
              here overrides it for this Page only.
            </>
          }
        >
          <PromptEditors pageId={pageId} />
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





/**
 * When this Page publishes.
 *
 * Policy rather than schedule state, which is the whole reason it can live in
 * our database at all without contradicting ADR-0001: a slot is a standing
 * decision — "we post at 08:00 and 19:00" — that exists whether or not anything
 * is queued against it. What is *actually* queued is still read live from
 * Metricool's planner, and "next available" checks these against that.
 *
 * No weekday dimension. The operator chose the same times every day; adding one
 * later is an additive migration rather than a rewrite.
 */
function TimeSlots({ pageId }: { pageId: number | null }) {
  const { data: slots, refresh } = useQuery(() => listSlots(pageId!), [pageId], {
    enabled: pageId !== null,
  });
  const [time, setTime] = useState("");
  const [saving, setSaving] = useState(false);

  async function add(event: React.FormEvent) {
    event.preventDefault();
    // `<input type="time">` gives `HH:MM`, which is the one format that needs
    // no parsing rules of our own.
    const [hour, minute] = time.split(":").map(Number);
    if (pageId === null || Number.isNaN(hour) || Number.isNaN(minute)) return;

    setSaving(true);
    try {
      await addSlot(pageId, hour, minute);
      setTime("");
      await refresh();
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "Could not add that time");
    } finally {
      setSaving(false);
    }
  }

  async function drop(id: number, label: string) {
    if (pageId === null) return;
    try {
      await removeSlot(pageId, id);
      toast.success(`${label} removed`);
      await refresh();
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "Could not remove");
    }
  }

  if (!slots) return <Skeleton className="h-24 rounded-lg" />;

  return (
    <div className="space-y-3">
      <form onSubmit={add} className="flex items-center gap-2">
        <Clock className="size-3.5 shrink-0 text-muted-foreground" />
        <Input
          type="time"
          value={time}
          onChange={(event) => setTime(event.target.value)}
          aria-label="Publishing time"
          className="h-8 w-32 text-xs"
        />
        <Button
          type="submit"
          size="sm"
          variant="outline"
          className="h-8"
          disabled={saving || !time || pageId === null}
        >
          {saving ? <Loader2 className="size-3 animate-spin" /> : "Add time"}
        </Button>
      </form>

      {slots.length === 0 ? (
        // Not decoration: with no slots, "Schedule next available" has nothing
        // to offer and the server answers 409 rather than guessing a time.
        <p className="rounded-lg border border-dashed p-4 text-center text-xs text-muted-foreground">
          No publishing times yet. Until one is added, &ldquo;Schedule next
          available&rdquo; has nothing to choose from.
        </p>
      ) : (
        <div className="flex flex-wrap gap-1.5">
          {slots.map((slot) => (
            <span
              key={slot.id}
              className="group flex items-center gap-1 rounded-full border py-1 pr-1 pl-2.5 text-xs tabular-nums"
            >
              {slot.label}
              <button
                type="button"
                onClick={() => void drop(slot.id, slot.label)}
                aria-label={`Remove ${slot.label}`}
                className="rounded-full p-0.5 text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
              >
                <Trash2 className="size-3" />
              </button>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

/** The house numbers, from `api/app/writer/validators.py`. Shown as the
 *  placeholder so an empty box reads as "65", not as "unset". */
const HOUSE = {
  hook_max_words: 65,
  first_comment_min_chars: 1500,
  first_comment_max_chars: 2100,
  first_comment_min_paragraphs: 2,
  first_comment_max_paragraphs: 3,
} as const;

type LimitField = keyof typeof HOUSE;

const LIMIT_ROWS: { field: LimitField; label: string }[] = [
  { field: "hook_max_words", label: "Hook, max words" },
  { field: "first_comment_min_chars", label: "First comment, min chars" },
  { field: "first_comment_max_chars", label: "First comment, max chars" },
  { field: "first_comment_min_paragraphs", label: "First comment, min paragraphs" },
  { field: "first_comment_max_paragraphs", label: "First comment, max paragraphs" },
];

/**
 * The five numbers, per Page (C6, C7).
 *
 * One Save for all five rather than a save per box, because they constrain each
 * other: a 1,500 ceiling is fine beside an 800 floor and impossible beside the
 * house 1,500. Saved one at a time, the operator would be refused halfway
 * through a change that is valid once finished.
 *
 * An emptied box sends null, never 0 — null is what returns the Page to the
 * house number, and 0 would be a Page that cannot write anything.
 */
function WritingLimits({ page }: { page: Page }) {
  const initial = () =>
    Object.fromEntries(
      LIMIT_ROWS.map(({ field }) => [field, page[field]?.toString() ?? ""]),
    ) as Record<LimitField, string>;

  const [form, setForm] = useState(initial);
  const [busy, setBusy] = useState(false);

  const dirty = LIMIT_ROWS.some(
    ({ field }) => form[field] !== (page[field]?.toString() ?? ""),
  );

  async function save() {
    setBusy(true);
    try {
      const update = Object.fromEntries(
        LIMIT_ROWS.map(({ field }) => [
          field,
          form[field].trim() === "" ? null : Number(form[field]),
        ]),
      );
      await updatePage(page.id, update);
      toast("Saved. New drafts for this Page use these lengths.");
      emit();
    } catch (cause) {
      // The API refuses a band no draft could satisfy, and its message names
      // the numbers. Surfaced verbatim: "cannot be both over 1,500 and under
      // 1,400" is the whole explanation, and a generic failure would send the
      // operator looking for a bug instead of a typo.
      toast.error(cause instanceof Error ? cause.message : "Could not save");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-3">
      {LIMIT_ROWS.map(({ field, label }) => (
        <div key={field} className="flex items-center gap-3">
          <Label className="flex-1 text-xs font-normal">{label}</Label>
          <Input
            type="number"
            inputMode="numeric"
            className="w-28"
            placeholder={String(HOUSE[field])}
            value={form[field]}
            onChange={(event) =>
              setForm({ ...form, [field]: event.target.value })
            }
          />
        </div>
      ))}

      <div className="flex items-center gap-3 pt-1">
        <Button size="sm" disabled={!dirty || busy} onClick={() => void save()}>
          {busy ? <Loader2 className="size-4 animate-spin" /> : null}
          Save lengths
        </Button>
        {dirty ? (
          <Button
            variant="ghost"
            size="sm"
            disabled={busy}
            onClick={() => setForm(initial)}
          >
            Revert
          </Button>
        ) : null}
      </div>
    </div>
  );
}

/** Where a prompt's text came from, in the words the operator needs. */
const SOURCE_LABEL: Record<PromptFile["source"], string> = {
  page: "this Page's own",
  "file-override": "file, api/prompts/pages/",
  global: "inherited from api/prompts/",
};

/**
 * The three prompts, editable per Page (F5).
 *
 * Each box shows the text **as sent**, which for an inherited prompt is the
 * global file's. That is deliberate and it is also the trap: typing into a box
 * that reads "inherited" and saving creates an override of the whole thing. The
 * label above each box says which of the three it is, and Save is disabled
 * until the text actually differs, so inheriting is never ended by accident.
 */
function PromptEditors({ pageId }: { pageId: number | null }) {
  const { data: files } = useQuery(() => listPromptFiles(pageId!), [pageId], {
    enabled: pageId !== null,
  });

  if (files === null) return <Skeleton className="h-64" />;

  return (
    <div className="space-y-6">
      {files.map((file) => (
        <PromptEditor key={file.filename} pageId={pageId!} file={file} />
      ))}
    </div>
  );
}

function PromptEditor({ pageId, file }: { pageId: number; file: PromptFile }) {
  const [text, setText] = useState(file.body);
  const [busy, setBusy] = useState(false);
  const dirty = text !== file.body;

  async function save(body: string) {
    setBusy(true);
    try {
      const saved = await setPromptFile(pageId, file.filename, body);
      toast(
        saved.source === "page"
          ? `${file.filename} is now this Page's own.`
          : `${file.filename} is back to the inherited prompt.`,
      );
      emit();
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "Could not save");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <Label className="font-mono text-xs">{file.filename}</Label>
        <span
          className={cn(
            "text-xs",
            file.source === "page"
              ? "font-medium text-foreground"
              : "text-muted-foreground",
          )}
        >
          {SOURCE_LABEL[file.source]}
        </span>
        <span className="text-xs text-muted-foreground">
          {file.chars.toLocaleString()} chars
        </span>
      </div>

      {file.editable ? (
        <>
          <Textarea
            rows={10}
            className="font-mono text-xs"
            value={text}
            onChange={(event) => setText(event.target.value)}
          />
          <div className="flex items-center gap-3">
            <Button
              size="sm"
              disabled={!dirty || busy}
              onClick={() => void save(text)}
            >
              {busy ? <Loader2 className="size-4 animate-spin" /> : null}
              Save for this Page
            </Button>
            {dirty ? (
              <Button
                variant="ghost"
                size="sm"
                disabled={busy}
                onClick={() => setText(file.body)}
              >
                Revert
              </Button>
            ) : null}
            {/* Only when there is an override to clear. On an inherited prompt
                this button would claim to undo something that is not there. */}
            {file.source === "page" ? (
              <Button
                variant="ghost"
                size="sm"
                disabled={busy}
                onClick={() => void save("")}
              >
                Use the default
              </Button>
            ) : null}
          </div>
        </>
      ) : (
        <>
          <pre className="max-h-48 overflow-auto rounded-lg border bg-muted/40 p-3 font-mono text-xs whitespace-pre-wrap">
            {file.body}
          </pre>
          <p className="text-xs text-muted-foreground">
            No per-Page column behind this one, so it is a file only.
          </p>
        </>
      )}
    </div>
  );
}
