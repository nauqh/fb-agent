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
import { Block, ConfigShell, Gap, Pane } from "@/components/config-shell";
import { Loading } from "@/components/loading";
import { ScreenHeader } from "@/components/screen";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
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
 *
 * **The screen is a rail and a pane** since 2026-08-17, not a grid of cards —
 * see `config-shell.tsx` for the measurement that killed the grid. The queries
 * all live here rather than in the sections that use them, because the rail
 * shows each section's count and whether it is empty, and a count cannot be
 * fetched by a component the rail is deciding whether to render.
 */
export default function SettingsScreen() {
  const { page, pageId } = usePageScope();

  const { data: sources } = useQuery(() => getSourcesConfig(pageId!), [pageId], {
    enabled: pageId !== null,
  });
  const { data: slots, refresh: refreshSlots } = useQuery(
    () => listSlots(pageId!),
    [pageId],
    { enabled: pageId !== null },
  );
  const { data: prompts } = useQuery(() => listPromptFiles(pageId!), [pageId], {
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
   * it reads only what is assigned. The hint under the pane says so, because
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
    return <Loading label="Loading this Page" className="h-96" />;
  }

  const assigned =
    pageId === null || !competitors
      ? 0
      : competitors.filter((one) => one.assigned_page_ids.includes(pageId)).length;

  const ownLengths = LIMIT_ROWS.filter(({ field }) => page[field] !== null).length;
  const ownPrompts = (prompts ?? []).filter((one) => one.source !== "global").length;

  /**
   * A Page told to write short by a prompt nothing enforces.
   *
   * This is C6/C7's failure mode as a live check rather than a note in a doc.
   * The two fitness Pages have their own prompt files asking for a 30-word hook
   * while all five length columns are null, so the validator still allows the
   * house 65 — the prompt asks and nothing holds it to it. Worth a triangle in
   * the rail, because no screen would otherwise show the disagreement.
   */
  const promptsWithoutLengths = ownPrompts > 0 && ownLengths === 0;

  return (
    <ConfigShell
      header={<ScreenHeader title="Settings" />}
      groups={[
        {
          label: "This Page",
          sections: [
            {
              id: "identity",
              label: "Identity",
              gap: !page.watermark_image_path && !page.watermark_upload_path,
              body: <Identity page={page} />,
            },
            {
              id: "feeds",
              label: "Feeds",
              meta: sources?.feeds.length ?? "",
              gap: sources ? sources.feeds.length === 0 : false,
              body: <Feeds pageId={pageId} sources={sources} />,
            },
            {
              id: "times",
              label: "Publishing times",
              meta: slots?.length ?? "",
              gap: slots ? slots.length === 0 : false,
              body: (
                <TimeSlots pageId={pageId} slots={slots} refresh={refreshSlots} />
              ),
            },
            {
              id: "writing",
              label: "Writing",
              meta: ownLengths > 0 ? `${ownLengths}/5` : "house",
              gap: promptsWithoutLengths,
              body: (
                <Writing
                  page={page}
                  ownPrompts={ownPrompts}
                  unenforced={promptsWithoutLengths}
                />
              ),
            },
            {
              id: "prompts",
              label: "Prompts",
              meta: prompts ? `${ownPrompts}/${prompts.length}` : "",
              body: <Prompts pageId={pageId} files={prompts} />,
            },
            {
              id: "competitors",
              label: "Competitors",
              meta: competitors ? assigned : "",
              body: (
                <Competitors
                  page={page}
                  pageId={pageId}
                  rows={competitors}
                  error={competitorsError}
                  loading={competitorsLoading}
                  onToggle={toggleAssignment}
                />
              ),
            },
          ],
        },
      ]}
    />
  );
}

/** What this Page is, all of it from Metricool except the mark. */
function Identity({ page }: { page: Page }) {
  const mark = page.watermark_upload_url
    ? page.watermark_upload_url
    : page.watermark_image_path
      ? `/api/${page.watermark_image_path}`
      : null;

  return (
    <Pane
      title={page.name}
      hint="Identity comes from Metricool and is not editable here."
    >
      <div className="space-y-6">
        <Block label="Ids">
          <dl className="space-y-2 text-[13px]">
            <Row label="Facebook">{page.facebook_page_id}</Row>
            <Row label="Metricool">{page.metricool_blog_id ?? "—"}</Row>
          </dl>
        </Block>

        <Block label="Watermark">
          {mark ? (
            <div className="flex items-center gap-3">
              {/* On black, because that is the only background it is ever drawn
                  against and it is white ink. */}
              <span className="rounded-md bg-black px-3 py-2">
                {/* eslint-disable-next-line @next/next/no-img-element -- a
                    committed asset at its natural ratio, not a content image. */}
                <img
                  src={mark}
                  alt={`${page.name} watermark`}
                  className="h-10 w-auto"
                />
              </span>
              <code className="min-w-0 truncate text-[13px] text-muted-foreground">
                {page.watermark_upload_path ?? page.watermark_image_path}
              </code>
            </div>
          ) : page.watermark_enabled ? (
            <Gap title="No watermark for this Page.">
              Its cards are stamped with the Page&rsquo;s name as text instead.
              A committed asset or an upload is what makes a picture traceable
              once it is reposted.
            </Gap>
          ) : (
            <p className="text-[13px] text-muted-foreground">
              Switched off. This Page&rsquo;s cards carry no mark at all.
            </p>
          )}
        </Block>
      </div>
    </Pane>
  );
}

/** A label/value line: name left, value right, the way a spec sheet reads. */
function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-dashed pb-2 last:border-0">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="truncate font-mono">{children}</dd>
    </div>
  );
}

function Feeds({
  pageId,
  sources,
}: {
  pageId: number | null;
  sources: Awaited<ReturnType<typeof getSourcesConfig>> | null;
}) {
  return (
    <Pane
      title="Feeds"
      hint={
        <>
          This Page&rsquo;s feeds. Adding one probes it first &mdash; a feed that
          does not answer is not saved.
        </>
      }
      meta={
        sources
          ? `${sources.feeds.length} feeds · ${sources.since_days}d window · ${sources.max_items} shown`
          : undefined
      }
    >
      {!sources ? (
        <Loading label="Loading feeds" className="h-40" />
      ) : (
        <div className="space-y-3">
          <div className="divide-y rounded-2xl border">
            <AddFeed pageId={pageId} />
            {sources.feeds.map((feed) => (
              // The row opens the feed itself. Checking a feed means looking at
              // what it is serving right now, and this screen is where you are
              // when you doubt one.
              <div
                key={feed.url}
                className="group flex items-center gap-3 px-3 py-2 text-[13px] hover:bg-muted/50"
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

          {sources.feeds.length === 0 ? (
            <Gap title="No feeds, so the RSS tab on Sources is empty for this Page.">
              Nothing is wrong with the fetch — there is nothing configured to
              fetch. Add a publisher above; it is probed before it is saved.
            </Gap>
          ) : null}
        </div>
      )}
    </Pane>
  );
}

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
        "flex shrink-0 items-center gap-1 rounded-md border px-2 py-1 text-xs transition-colors",
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

function Competitors({
  page,
  pageId,
  rows,
  error,
  loading,
  onToggle,
}: {
  page: Page;
  pageId: number | null;
  rows: Awaited<ReturnType<typeof getCompetitorPages>> | null;
  error: string | null;
  loading: boolean;
  onToggle: (providerId: string) => void;
}) {
  const assigned =
    pageId === null || !rows
      ? 0
      : rows.filter((one) => one.assigned_page_ids.includes(pageId)).length;
  const silent = (rows ?? []).filter((one) => one.posts_stored === 0).length;

  return (
    <Pane
      title="Competitors this Page reads"
      hint={
        <>
          Which of the pool this Page reads. Tick to assign; the same source can
          feed several Pages. The pool itself is on Global.
        </>
      }
      meta={
        rows ? (
          <>
            {assigned} of {rows.length} assigned
            {silent ? (
              <span className="text-destructive"> · {silent} silent</span>
            ) : null}
          </>
        ) : undefined
      }
    >
      {error ? (
        // This section fails alone. Everything else on the screen is a local
        // file or our own database and cannot.
        <p className="rounded-2xl border border-dashed p-4 text-[13px] text-destructive">
          {error}
        </p>
      ) : loading || !rows ? (
        <Loading label="Reading Metricool" className="h-40" />
      ) : (
        <div className="space-y-3">
          {assigned === 0 ? (
            <Gap title="Nothing assigned, so this Page falls back to its own Metricool set.">
              That is not the same list — it is whatever competitors happen to
              sit under this brand in Metricool, which is a decision nobody made
              on purpose. Assign the ones it should read.
            </Gap>
          ) : null}

          {/* A grid, not one long list: twenty-six full-width rows is a scroll,
              and the row has three short fields in it. Silent ones come first
              from the server, so reading order still puts the finding at the
              top left. */}
          <div className="grid gap-2 sm:grid-cols-2 2xl:grid-cols-3">
            {rows.map((competitor) => (
              // `provider_id` is the Facebook page id, which is all
              // facebook.com needs — no screen name to go stale. A silent
              // competitor is the row you most want to open: it answers whether
              // the page died or merely went quiet.
              <div
                key={competitor.provider_id}
                className={cn(
                  "group flex items-center gap-2.5 rounded-lg border px-3 py-2 text-[13px] transition-colors hover:bg-muted/50",
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
                  onToggle={() => onToggle(competitor.provider_id)}
                />
              </div>
            ))}
          </div>
        </div>
      )}
    </Pane>
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
        className="h-7 w-32 shrink-0 text-[13px]"
      />
      <Input
        value={url}
        onChange={(event) => setUrl(event.target.value)}
        placeholder="https://example.com/feed"
        aria-label="Feed URL"
        className="h-7 min-w-0 flex-1 text-[13px]"
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
function TimeSlots({
  pageId,
  slots,
  refresh,
}: {
  pageId: number | null;
  slots: Awaited<ReturnType<typeof listSlots>> | null;
  refresh: () => Promise<void> | void;
}) {
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

  return (
    <Pane
      title="Publishing times"
      hint={
        <>
          The slots &ldquo;Schedule next available&rdquo; walks through. The same
          times every day, in this Page&rsquo;s zone (GMT+7).
        </>
      }
      meta={slots ? `${slots.length} a day` : undefined}
    >
      {!slots ? (
        <Loading label="Loading times" className="h-24" />
      ) : (
        <div className="space-y-4">
          <form onSubmit={add} className="flex items-center gap-2">
            <Clock className="size-3.5 shrink-0 text-muted-foreground" />
            <Input
              type="time"
              value={time}
              onChange={(event) => setTime(event.target.value)}
              aria-label="Publishing time"
              className="h-8 w-32 text-[13px]"
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
            // Not decoration: with no slots, "Schedule next available" has
            // nothing to offer and the server answers 409 rather than guessing.
            <Gap title="No publishing times, so “Schedule next available” cannot run.">
              It answers 409 rather than inventing a time. Publish now and
              Publish at a time both still work.
            </Gap>
          ) : (
            <div className="flex flex-wrap gap-1.5">
              {slots.map((slot) => (
                <span
                  key={slot.id}
                  className="group flex items-center gap-1 rounded-full border py-1 pr-1 pl-2.5 text-[13px] tabular-nums"
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
      )}
    </Pane>
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

const LIMIT_ROWS: { field: LimitField; label: string; group: string }[] = [
  { field: "hook_max_words", label: "Max words", group: "Hook" },
  { field: "first_comment_min_chars", label: "Min chars", group: "First comment" },
  { field: "first_comment_max_chars", label: "Max chars", group: "First comment" },
  { field: "first_comment_min_paragraphs", label: "Min ¶", group: "First comment" },
  { field: "first_comment_max_paragraphs", label: "Max ¶", group: "First comment" },
];

function Writing({
  page,
  ownPrompts,
  unenforced,
}: {
  page: Page;
  ownPrompts: number;
  unenforced: boolean;
}) {
  return (
    <Pane
      title="How this Page writes"
      hint={
        <>
          Leave a box empty to use the house number. These are the lengths the
          writer is told to hit <em>and</em> the ones a draft is checked against
          &mdash; they cannot disagree.
        </>
      }
    >
      <div className="space-y-5">
        {unenforced ? (
          <Gap
            title={`This Page has ${ownPrompts === 1 ? "its own prompt" : `${ownPrompts} prompts of its own`} but house lengths.`}
          >
            A prompt asking for a shorter hook is a request; the validator is
            what enforces it. While every box below is empty, a draft is checked
            against {HOUSE.hook_max_words} words and {HOUSE.first_comment_min_chars}–
            {HOUSE.first_comment_max_chars} characters whatever the prompt says.
          </Gap>
        ) : null}

        <WritingLimits page={page} />
      </div>
    </Pane>
  );
}

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

  // Grouped by the thing being measured, so "Hook" is one box and "First
  // comment" is four — five identical full-width rows read as five unrelated
  // settings and took 250px to carry five numbers.
  const groups = [...new Set(LIMIT_ROWS.map((row) => row.group))];

  return (
    <div className="space-y-5">
      {groups.map((group) => (
        <Block key={group} label={group}>
          <div className="grid gap-3 sm:grid-cols-2">
            {LIMIT_ROWS.filter((row) => row.group === group).map(
              ({ field, label }) => (
                <div
                  key={field}
                  className="flex items-center justify-between gap-3 rounded-2xl border px-3 py-2"
                >
                  <Label className="text-[13px] font-normal text-muted-foreground">
                    {label}
                  </Label>
                  <Input
                    type="number"
                    inputMode="numeric"
                    aria-label={`${group} — ${label}`}
                    className={cn(
                      "h-7 w-20 border-0 bg-transparent px-1 text-right tabular-nums shadow-none focus-visible:ring-0",
                      // An inherited value is the placeholder, so the box must
                      // not look like it holds a number of its own.
                      form[field] === "" ? "text-muted-foreground" : "font-medium",
                    )}
                    placeholder={String(HOUSE[field])}
                    value={form[field]}
                    onChange={(event) =>
                      setForm({ ...form, [field]: event.target.value })
                    }
                  />
                </div>
              ),
            )}
          </div>
        </Block>
      ))}

      <div className="flex items-center gap-3">
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
        <p className="text-[13px] text-muted-foreground">
          Empty inherits the house number, shown greyed.
        </p>
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
 *
 * One prompt at a time since 2026-08-17. Three 10-row textareas stacked made a
 * 1,400px section in which the one being edited was usually off screen.
 */
function Prompts({
  pageId,
  files,
}: {
  pageId: number | null;
  files: PromptFile[] | null;
}) {
  // Not seeded from `files` — it arrives a render after this component
  // mounts, and a value chosen at mount cannot know the real filenames yet.
  // `active` falls back to the first file whenever `open` names none of them,
  // which covers that gap with no effect needed to correct it later.
  const [open, setOpen] = useState<string>("");
  const active = files?.find((file) => file.filename === open) ?? files?.[0];

  return (
    <Pane
      title="Prompts"
      hint={
        <>
          What this Page tells the model. Empty means it inherits the reviewed
          default in <code>api/prompts/</code> &mdash; saving text here overrides
          it for this Page only.
        </>
      }
      meta={files ? `${files.filter((one) => one.source !== "global").length} overridden` : undefined}
    >
      {files === null ? (
        <Loading label="Loading prompts" className="h-64" />
      ) : (
        <div className="space-y-4">
          {/* The shared pill shell (`ui/tabs.tsx`) rather than a second
              hand-rolled one: the three are alternatives, not a list, and
              which one you are editing has to stay visible while the textarea
              is 400px tall. */}
          <Tabs value={active?.filename ?? ""} onValueChange={setOpen}>
            <TabsList className="w-fit">
              {files.map((file) => (
                <TabsTrigger
                  key={file.filename}
                  value={file.filename}
                  className="font-mono"
                >
                  {file.filename}
                  {file.source !== "global" ? (
                    <span
                      aria-label="overridden"
                      className={cn(
                        "size-1.5 rounded-full",
                        active?.filename === file.filename
                          ? "bg-background"
                          : "bg-foreground",
                      )}
                    />
                  ) : null}
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>

          {active ? (
            <PromptEditor key={active.filename} pageId={pageId!} file={active} />
          ) : null}
        </div>
      )}
    </Pane>
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
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px]">
        <span
          className={cn(
            file.source === "page"
              ? "font-medium text-foreground"
              : "text-muted-foreground",
          )}
        >
          {SOURCE_LABEL[file.source]}
        </span>
        <span className="text-muted-foreground">
          {file.chars.toLocaleString()} chars
        </span>
      </div>

      {file.editable ? (
        <>
          <Textarea
            rows={18}
            className="font-mono text-[13px]"
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
          <pre className="max-h-96 overflow-auto rounded-2xl border bg-muted/40 p-3 font-mono text-[13px] whitespace-pre-wrap">
            {file.body}
          </pre>
          <p className="text-[13px] text-muted-foreground">
            No per-Page column behind this one, so it is a file only.
          </p>
        </>
      )}
    </div>
  );
}
