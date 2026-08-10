"use client";

import { useState } from "react";
import { ChevronDown, ExternalLink, FileText, Loader2, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { CompetitorMark } from "@/components/competitor-mark";
import { Card, Counts } from "@/components/config-card";
import { QueuePagination } from "@/components/queue-pagination";
import { ScreenHeader } from "@/components/screen";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  addToPool,
  getAllowance,
  removeFromPool,
  type Allowance,
} from "@/lib/api/competitors";
import { getLayout } from "@/lib/api/config";
import { listPromptFiles } from "@/lib/api/pages";
import { getCompetitorPages, type CompetitorPage } from "@/lib/api/sources";
import { usePageScope } from "@/lib/page-scope";
import { emit } from "@/lib/store";
import { useQuery } from "@/lib/use-query";
import { cn } from "@/lib/utils";

/**
 * What belongs to the account rather than to a Page.
 *
 * Split out of Settings because the two answer different questions and mixing
 * them put an account-wide number under a per-Page heading — "48 configured"
 * beside a Page name, when 48 was neither that Page's nor the account's total.
 *
 * Here: the competitor pool and its Metricool budget. On Settings: which of
 * this pool a given Page reads, plus that Page's feeds and watermark.
 */
export default function GlobalScreen() {
  const { pages } = usePageScope();

  const { data: allowance } = useQuery(() => getAllowance(), []);
  const { data: layout } = useQuery(() => getLayout(), []);
  const { data: prompts } = useQuery(() => listPromptFiles(), []);
  const {
    data: pool,
    error: poolError,
    loading: poolLoading,
  } = useQuery(() => getCompetitorPages(), []);

  return (
    // Its own scroller, like every screen: the shell is `lg:overflow-hidden` on
    // both `body` and `main`, so a screen without `overflow-y-auto` here is not
    // a short page — it is a clipped one, with everything below the fold simply
    // unreachable. `pb-16` keeps the last row clear of the mobile bar.
    <div className="w-full space-y-4 pb-16 lg:min-h-0 lg:flex-1 lg:overflow-y-auto lg:pr-3">
      <ScreenHeader title="Global" />

      <Budget data={allowance} />

      <Card
        title="Competitor pool"
        hint={
          <>
            Every page Metricool is watching, across the whole account. Add one
            here; choose which of your Pages read it on Settings.
          </>
        }
        meta={
          pool ? (
            <Counts>
              {pool.length} watched
              {(() => {
                const silent = pool.filter((one) => one.posts_stored === 0).length;
                return silent ? (
                  <span className="text-destructive"> · {silent} silent</span>
                ) : null;
              })()}
            </Counts>
          ) : null
        }
      >
        <AddToPool />

        {poolError ? (
          <p className="rounded-lg border border-dashed p-4 text-xs text-destructive">
            {poolError}
          </p>
        ) : poolLoading || !pool ? (
          <Skeleton className="h-64 rounded-lg" />
        ) : (
          <PoolTable rows={pool} pages={pages} />
        )}
      </Card>

      <div className="grid items-start gap-4 xl:grid-cols-2">
        <Card
          title="Composed Image"
          hint={<><code>api/config/layout.yml</code>, read back from the server.</>}
        >
          {layout ? (
            <dl className="grid grid-cols-2 gap-x-6 gap-y-3 text-xs sm:grid-cols-4">
              <Constant
                label="Size"
                value={`${layout.image.width} × ${layout.image.height}`}
              />
              <Constant
                label="Panel"
                value={`${Math.round(layout.panel.ratio * 100)}–${Math.round(layout.panel.max_ratio * 100)}%`}
              />
              <Constant
                label="Font"
                value={`${layout.font.family} ${layout.font.weight} ${layout.text.font_size_px}px`}
              />
              <Constant label="Highlight" value={layout.highlight.color} swatch />
            </dl>
          ) : (
            <Skeleton className="h-16 rounded-lg" />
          )}
        </Card>

        <Card
          title="Prompts"
          hint={<>Files in <code>api/prompts/</code>, edited in your editor.</>}
        >
          <div className="divide-y rounded-lg border">
            {prompts?.map((prompt) => (
              <PromptRow key={prompt.filename} {...prompt} />
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}

/**
 * How much of Metricool's competitor limit is spent.
 *
 * A meter rather than a number in a corner, because this is the only figure on
 * either screen that stops you doing something. Segmented by brand so the
 * answer to "where did it go" is in the same object as "how much is left" —
 * on this account 44 of 92 sit on brands with no Page in this app, and a bare
 * total would send someone hunting through Metricool for them.
 *
 * 100 is Metricool's published figure for Starter and Advanced alike. Their
 * documentation does not say whether it counts per account or per brand; the
 * number staying at 100 while brands go from 10 to 50 is the reason to read it
 * as per account. If that turns out to be wrong this bar is pessimistic, which
 * is the safe direction for a limit.
 */
function Budget({ data }: { data: Allowance | null }) {
  if (!data) return <Skeleton className="h-24 rounded-xl" />;

  const spent = data.profiles.filter((one) => one.competitors > 0);
  // Brands watching nobody are left out of the bar — a zero-width segment is
  // invisible — but they are counted at the end, because "why only four when I
  // have eleven brands?" is the first question the legend otherwise raises.
  const empty = data.profiles.length - spent.length;
  const tight = data.remaining <= 10;

  return (
    <section
      className={cn(
        "rounded-xl border bg-card p-5",
        tight && "border-destructive/40",
      )}
    >
      <div className="flex items-end justify-between gap-4 pb-3">
        <div>
          <h2 className="text-sm font-medium">Metricool competitor budget</h2>
          <p className="pt-1 text-xs text-muted-foreground">
            One allowance for the whole account, shared by every brand.
          </p>
        </div>
        <p className="shrink-0 text-right">
          <span
            className={cn(
              "text-2xl font-semibold tabular-nums",
              tight && "text-destructive",
            )}
          >
            {data.remaining}
          </span>
          <span className="pl-1.5 text-xs text-muted-foreground">
            left of {data.limit}
          </span>
        </p>
      </div>

      {/* Segmented, not a single fill: the segments are the brands, and the gap
          between them is what makes four of eleven readable at a glance. */}
      <div className="flex h-2 w-full gap-0.5 overflow-hidden rounded-full bg-muted">
        {spent.map((profile) => (
          <div
            key={profile.blog_id}
            title={`${profile.label} — ${profile.competitors}`}
            style={{ width: `${(profile.competitors / data.limit) * 100}%` }}
            className={cn(
              "h-full first:rounded-l-full",
              profile.managed ? "bg-primary" : "bg-muted-foreground/40",
            )}
          />
        ))}
      </div>

      <ul className="flex flex-wrap gap-x-4 gap-y-1 pt-3 text-xs">
        {spent.map((profile) => (
          <li key={profile.blog_id} className="flex items-center gap-1.5">
            <span
              className={cn(
                "size-2 rounded-full",
                profile.managed ? "bg-primary" : "bg-muted-foreground/40",
              )}
            />
            <span className={profile.managed ? "font-medium" : "text-muted-foreground"}>
              {profile.label}
            </span>
            <span className="tabular-nums text-muted-foreground">
              {profile.competitors}
            </span>
            {/* Named rather than implied. A brand with no Page here still spends
                the allowance, and that is the surprising half. */}
            {!profile.managed ? (
              <span className="text-muted-foreground">· not in this app</span>
            ) : null}
          </li>
        ))}
        {empty > 0 ? (
          <li className="text-muted-foreground">
            + {empty} brand{empty === 1 ? "" : "s"} watching nobody
          </li>
        ) : null}
      </ul>
    </section>
  );
}

/**
 * Add a page to the pool.
 *
 * Metricool has no account-level list — a competitor belongs to a brand — so
 * this has to name one. It decides only where the allowance is spent, not who
 * reads it: any Page can be assigned the result afterwards.
 */
function AddToPool() {
  const { pages, pageId } = usePageScope();
  const [under, setUnder] = useState<number | null>(null);
  const [value, setValue] = useState("");
  const [saving, setSaving] = useState(false);

  const target = under ?? pageId;

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (target === null || !value.trim()) return;

    setSaving(true);
    try {
      await addToPool(target, value.trim());
      toast.success("Added to the pool");
      setValue("");
      emit();
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "Could not add that page");
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={submit} className="mb-4 flex flex-wrap items-center gap-2">
      <Plus className="size-3.5 shrink-0 text-muted-foreground" />
      <Input
        value={value}
        onChange={(event) => setValue(event.target.value)}
        placeholder="Facebook page id, e.g. 20528438720"
        aria-label="Facebook page id"
        className="h-8 min-w-48 flex-1 text-xs"
      />
      <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
        under
        <select
          value={target ?? ""}
          onChange={(event) => setUnder(Number(event.target.value))}
          className="h-8 rounded-md border bg-background px-2 text-xs"
          aria-label="Which brand to add it under"
        >
          {pages.map((page) => (
            <option key={page.id} value={page.id}>
              {page.name}
            </option>
          ))}
        </select>
      </label>
      <Button
        type="submit"
        size="sm"
        variant="outline"
        className="h-8 shrink-0"
        disabled={saving || target === null || !value.trim()}
      >
        {saving ? <Loader2 className="size-3.5 animate-spin" /> : "Add"}
      </Button>
    </form>
  );
}

/** Rows per page. Larger than the Review queue's ten because these rows are a
 *  single line each rather than a 120px composite. */
const POOL_PAGE_SIZE = 12;

/**
 * The pool itself.
 *
 * A table rather than the card grid Settings uses, because these rows are read
 * as a list — which brand, how many Pages read it, is it producing — and four
 * short columns compare down a column far better than across a card.
 *
 * Silent ones come first from the server: a competitor configured and producing
 * nothing looks exactly like one that was never configured, from every other
 * screen.
 */
function PoolTable({
  rows,
  pages,
}: {
  rows: CompetitorPage[];
  pages: { id: number; name: string }[];
}) {
  const nameOf = new Map(pages.map((page) => [page.id, page.name]));
  const [page, setPage] = useState(1);

  // Clamped rather than reset: removing the last row of the last page should
  // step back a page, not throw the operator to the top of a 48-row list.
  const totalPages = Math.max(1, Math.ceil(rows.length / POOL_PAGE_SIZE));
  const current = Math.min(page, totalPages);
  const shown = rows.slice((current - 1) * POOL_PAGE_SIZE, current * POOL_PAGE_SIZE);

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[46rem] text-xs">
        <thead>
          <tr className="border-b text-left text-muted-foreground">
            <th className="pb-2 font-normal">Page</th>
            <th className="pb-2 font-normal">In brand</th>
            <th className="pb-2 font-normal">Read by</th>
            <th className="pb-2 text-right font-normal">Posts</th>
            <th className="pb-2" />
          </tr>
        </thead>
        <tbody className="divide-y">
          {shown.map((row) => (
            <tr key={`${row.page_id}-${row.provider_id}`} className="group">
              <td className="py-2 pr-3">
                {/* The logo is how a competitor is actually recognised — several
                    of these are "Historical facts" / "History Addicts" /
                    "History Remembered", which do not tell apart by name. */}
                <div className="flex min-w-0 items-center gap-2.5">
                  <CompetitorMark
                    name={row.name}
                    picture={row.picture}
                    className="size-7"
                  />
                  <div className="min-w-0">
                    <a
                      href={`https://www.facebook.com/${row.provider_id}`}
                      target="_blank"
                      rel="noreferrer"
                      className="flex min-w-0 items-center gap-1.5 font-medium hover:underline"
                    >
                      <span className="truncate">{row.name}</span>
                      <ExternalLink className="size-3 shrink-0 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" />
                    </a>
                    <span className="block text-muted-foreground tabular-nums">
                      {(row.followers ?? 0).toLocaleString()} followers
                    </span>
                  </div>
                </div>
              </td>
              <td className="py-2 pr-3 text-muted-foreground">{row.page_name}</td>
              <td className="py-2 pr-3">
                {row.assigned_page_ids.length === 0 ? (
                  // Not an error: a Page with no assignments at all still reads
                  // its own brand's set through the fallback. Settings is where
                  // that gets decided, so this points there rather than warning.
                  <span className="text-muted-foreground">not assigned</span>
                ) : (
                  row.assigned_page_ids
                    .map((id) => nameOf.get(id) ?? id)
                    .join(", ")
                )}
              </td>
              <td
                className={cn(
                  "py-2 pr-3 text-right tabular-nums",
                  row.posts_stored === 0 ? "text-destructive" : "text-muted-foreground",
                )}
              >
                {row.posts_stored === 0 ? "none" : row.posts_stored}
              </td>
              <td className="py-2 text-right">
                <RemoveFromPool
                  id={row.id}
                  pageId={row.page_id}
                  name={row.name}
                  assigned={row.assigned_page_ids.length}
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {/* Paged rather than scrolled. Forty-eight rows is three screens, and the
          reason to look at this table is to compare — which brand, who reads it,
          is it producing — which a column running off the bottom defeats. The
          pager hides itself when everything already fits. */}
      <QueuePagination
        totalItems={rows.length}
        page={current}
        pageSize={POOL_PAGE_SIZE}
        onPageChange={setPage}
      />
    </div>
  );
}

/** Frees a slot in Metricool. Assignments naming it are left alone — re-adding
 *  the same page should bring them back rather than need re-ticking. */
function RemoveFromPool({
  id,
  pageId,
  name,
  assigned,
}: {
  id: number | null;
  pageId: number;
  name: string;
  assigned: number;
}) {
  const [busy, setBusy] = useState(false);

  async function remove() {
    if (id === null) return;
    setBusy(true);
    try {
      await removeFromPool(id, pageId);
      toast.success(
        assigned > 0
          ? `${name} removed — ${assigned} page assignment${assigned === 1 ? "" : "s"} kept`
          : `${name} removed`,
      );
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
      disabled={busy || id === null}
      aria-label={`Stop watching ${name}`}
      title={`Stop watching ${name}`}
      className="rounded p-1 text-muted-foreground opacity-0 transition-opacity hover:bg-destructive/10 hover:text-destructive group-hover:opacity-100 focus-visible:opacity-100 disabled:opacity-30"
    >
      {busy ? <Loader2 className="size-3 animate-spin" /> : <Trash2 className="size-3" />}
    </button>
  );
}

function Constant({
  label,
  value,
  swatch,
}: {
  label: string;
  value: string;
  swatch?: boolean;
}) {
  return (
    <div>
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="flex items-center gap-1.5 pt-0.5 font-mono">
        {swatch ? (
          <span
            className="size-2.5 rounded-full border"
            style={{ backgroundColor: value }}
          />
        ) : null}
        {value}
      </dd>
    </div>
  );
}

function PromptRow({
  filename,
  chars,
  body,
}: {
  filename: string;
  chars: number;
  body: string;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen((current) => !current)}
        className="flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-muted/50"
      >
        <FileText className="size-4 shrink-0 text-muted-foreground" />
        <span className="flex-1 font-mono text-xs">{filename}</span>
        <span className="tabular-nums text-xs text-muted-foreground">
          {chars.toLocaleString()} chars
        </span>
        <ChevronDown
          className={cn("size-4 text-muted-foreground transition-transform", open && "rotate-180")}
        />
      </button>
      {open ? (
        <pre className="max-h-96 overflow-auto whitespace-pre-wrap border-t bg-muted/40 px-4 py-3 font-mono text-[11px] leading-relaxed text-muted-foreground">
          {body}
        </pre>
      ) : null}
    </div>
  );
}
