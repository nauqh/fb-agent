"use client";

import { useState } from "react";
import {
  ArrowRight,
  ExternalLink,
  Loader2,
  Plus,
  Trash2,
} from "lucide-react";
import { toast } from "sonner";

import { CompetitorMark } from "@/components/competitor-mark";
import { ConfigShell, Pane } from "@/components/config-shell";
import { LayoutEditor } from "@/components/layout-editor";
import { PageSwitcher } from "@/components/page-switcher";
import { QueuePagination } from "@/components/queue-pagination";
import { ScreenHeader } from "@/components/screen";
import { Loading } from "@/components/loading";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  addToPool,
  getAllowance,
  removeFromPool,
  type Allowance,
} from "@/lib/api/competitors";
import { getCompetitorPages, type CompetitorPage } from "@/lib/api/sources";
import { usePageScope } from "@/lib/page-scope";
import type { Page } from "@/lib/types";
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
 *
 * **Prompts left this screen on 2026-08-17.** They were here read-only, under a
 * hint saying they are "edited in your editor" — which stopped being true the
 * day Settings grew an editor for them, leaving the same three files described
 * two ways on two screens. They are per-Page, so they live with the Page's other
 * per-Page settings and only there.
 *
 * The two screens are also **fully separate**: no rail entry here points at
 * Settings, and none there points here. Two scopes, two screens, no seam.
 */
export default function GlobalScreen() {
  const { pages } = usePageScope();

  const { data: allowance } = useQuery(() => getAllowance(), []);
  const {
    data: pool,
    error: poolError,
    loading: poolLoading,
  } = useQuery(() => getCompetitorPages(), []);

  return (
    <ConfigShell
      // No switcher in the title row. The pool is account-wide, and a Page name
      // up there read as the scope of the whole screen. Composed Image carries
      // its own switcher, beside the sentence saying it is per-Page.
      header={<ScreenHeader title="Global" switcher={false} />}
      groups={[
        {
          label: "Account",
          sections: [
            {
              id: "pool",
              label: "Competitor pool",
              meta: allowance ? `${allowance.remaining} left` : "",
              // The one number on either screen that stops you doing something.
              gap: allowance ? allowance.remaining <= 10 : false,
              body: (
                <CompetitorPool
                  allowance={allowance}
                  rows={pool}
                  pages={pages}
                  error={poolError}
                  loading={poolLoading}
                />
              ),
            },
            {
              id: "card",
              label: "Composed Image",
              body: (
                <Pane
                  title="Composed Image"
                  hint={
                    <>
                      <code>api/config/layout.yml</code> holds the defaults; what
                      you change here applies to the Page in the switcher only.
                    </>
                  }
                  action={<PageSwitcher />}
                >
                  <LayoutEditor />
                </Pane>
              ),
            },
          ],
        },
      ]}
    />
  );
}

/**
 * The pool and the budget that constrains it, as one object.
 *
 * They were two cards, and they duplicated each other: the budget said "92 of
 * 100, by brand", the pool said "92 watched", and brand appeared in both with
 * no link between them. The screen made you read the same number twice and
 * join it yourself.
 *
 * The join is the design. Metricool's segments *are* the pool's brands, so the
 * meter's segments and the filter chips are the same list, and picking a brand
 * both narrows the table and lights the slice of the bar that brand spent. The
 * question this screen exists to answer — "where did the hundred go, and is any
 * of it producing anything" — is then one gesture rather than two screens'
 * worth of arithmetic.
 *
 * 100 is Metricool's published figure for Starter and Advanced alike. Their
 * documentation does not say whether it counts per account or per brand; the
 * number staying at 100 while brands go from 10 to 50 is the reason to read it
 * as per account. If that turns out to be wrong this bar is pessimistic, which
 * is the safe direction for a limit.
 */
function CompetitorPool({
  allowance,
  rows,
  pages,
  error,
  loading,
}: {
  allowance: Allowance | null;
  rows: CompetitorPage[] | null;
  pages: Page[];
  error: string | null;
  loading: boolean;
}) {
  // Null is "no filter", which is not the same as any page id — hence null
  // rather than 0, which is a legal id in a table that starts at 1.
  const [brand, setBrand] = useState<number | null>(null);
  const [silentOnly, setSilentOnly] = useState(false);
  const [page, setPage] = useState(1);

  /** Every filter resets to the first page. Landing on page 4 of a two-page
   *  result is the classic way a filter looks like it returned nothing. */
  function filter(next: () => void) {
    next();
    setPage(1);
  }

  // Keyed by our Page id, because that is what the pool rows carry. The join to
  // Metricool's profiles is `metricool_blog_id` — exact, unlike matching on the
  // display name, which is the same string only by convention.
  const blogIdOf = new Map(pages.map((one) => [one.id, one.metricool_blog_id]));
  const selectedBlogId = brand === null ? null : blogIdOf.get(brand) ?? null;

  const counts = new Map<number, { name: string; total: number; silent: number }>();
  for (const row of rows ?? []) {
    const seen = counts.get(row.page_id) ?? { name: row.page_name, total: 0, silent: 0 };
    seen.total += 1;
    if (row.posts_stored === 0) seen.silent += 1;
    counts.set(row.page_id, seen);
  }
  const brands = [...counts.entries()].sort((a, b) => b[1].total - a[1].total);

  const silent = (rows ?? []).filter((one) => one.posts_stored === 0).length;
  const shown = (rows ?? []).filter(
    (row) =>
      (brand === null || row.page_id === brand) &&
      (!silentOnly || row.posts_stored === 0),
  );

  const tight = allowance ? allowance.remaining <= 10 : false;

  return (
    // Deliberately not a red border when the allowance is tight, which is what
    // the budget did as its own card. This card is now the whole screen's
    // subject, and ringing all of it in red says "everything here is wrong"
    // rather than "you have eight slots left" — the warning belongs on the
    // figure and on the empty end of the bar, which is where it is.
    <section className="overflow-hidden rounded-2xl border bg-card">
      <div className="p-5 pb-4">
        <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-2">
          <div className="min-w-0">
            <h2 className="text-base font-semibold tracking-tight">
              Competitor pool
            </h2>
            <p className="pt-1 text-[13px] text-muted-foreground">
              Every page Metricool is watching, on one allowance shared by every
              brand. Which of your Pages read one is set on Settings.
            </p>
          </div>

          {/* The remaining count, not the used count. This is the only figure on
              either screen that stops you doing something, and "8 left" is the
              form that says so. */}
          {allowance ? (
            <p className="shrink-0 text-right leading-none">
              <span
                className={cn(
                  "text-2xl font-semibold tabular-nums",
                  tight && "text-destructive",
                )}
              >
                {allowance.remaining}
              </span>
              <span className="pl-1.5 text-[13px] text-muted-foreground">
                left of {allowance.limit}
              </span>
            </p>
          ) : null}
        </div>

        <div className="pt-4">
          {allowance ? (
            <Meter data={allowance} selected={selectedBlogId} tight={tight} />
          ) : (
            // The one skeleton left in the app, and the one place it is still
            // right: the meter is an 8px bar, a spinner does not fit in it, and
            // a grey bar really is the shape of what is coming.
            <Skeleton className="h-2 rounded-full" />
          )}
        </div>

        {/* The legend and the filter are one control. A brand's chip carries the
            count that brand spent, so reading the bar and narrowing the table
            below are the same act. */}
        <div className="flex flex-wrap items-center gap-1.5 pt-4">
          <Chip active={brand === null} onClick={() => filter(() => setBrand(null))}>
            All
            <ChipCount active={brand === null}>{rows?.length ?? 0}</ChipCount>
          </Chip>

          {brands.map(([id, one]) => (
            <Chip
              key={id}
              active={brand === id}
              onClick={() => filter(() => setBrand(brand === id ? null : id))}
            >
              {one.name}
              <ChipCount active={brand === id}>{one.total}</ChipCount>
            </Chip>
          ))}

          {/* Silent is a filter rather than a red number in the corner, because
              it is the only thing on this screen that is actionable per row:
              these are slots being spent on nothing. It also explains the sort —
              the server puts silent sources first, and without this the list
              opens on a dozen rows reading "none" for no visible reason. */}
          {silent > 0 ? (
            <Chip
              tone="destructive"
              active={silentOnly}
              onClick={() => filter(() => setSilentOnly((current) => !current))}
            >
              {silent} silent
            </Chip>
          ) : null}

          <span className="ml-auto text-[13px] text-muted-foreground">
            <Unmanaged data={allowance} />
          </span>
        </div>
      </div>

      <div className="border-t px-5 py-4">
        <AddToPool />

        {error ? (
          <p className="rounded-2xl border border-dashed p-4 text-[13px] text-destructive">
            {error}
          </p>
        ) : loading || !rows ? (
          <Loading label="Reading Metricool" className="h-64" />
        ) : shown.length === 0 ? (
          <p className="rounded-2xl border border-dashed p-6 text-center text-[13px] text-muted-foreground">
            Nothing matches that filter.
          </p>
        ) : (
          <PoolTable rows={shown} pages={pages} page={page} onPageChange={setPage} />
        )}
      </div>
    </section>
  );
}

/**
 * The allowance as one bar, segmented by the brand that spent each slice.
 *
 * Segmented rather than a single fill because "where did it go" and "how much is
 * left" are the same question here, and the gap between segments is what makes
 * four brands out of eleven readable at a glance.
 *
 * Selection dims rather than recolours. The palette is neutral by design, so
 * four brands cannot each have a hue — instead the selected brand's segment
 * stays solid and the rest drop back, which reads the same in light and dark
 * and needs no legend swatches to decode.
 */
function Meter({
  data,
  selected,
  tight,
}: {
  data: Allowance;
  selected: string | null;
  tight: boolean;
}) {
  // Brands watching nobody are left out — a zero-width segment is invisible —
  // but `Unmanaged` still counts them, because "why only four when I have
  // eleven brands?" is the first question the bar otherwise raises.
  const spent = data.profiles.filter((one) => one.competitors > 0);

  return (
    // The *track* carries the warning, not the card: what turns red when the
    // account runs out of room is the part that is running out.
    <div
      className={cn(
        "flex h-2 w-full gap-0.5 overflow-hidden rounded-full transition-colors",
        tight ? "bg-destructive/25" : "bg-muted",
      )}
    >
      {spent.map((profile) => {
        const dimmed = selected !== null && profile.blog_id !== selected;
        return (
          <div
            key={profile.blog_id}
            title={`${profile.label} — ${profile.competitors}`}
            style={{ width: `${(profile.competitors / data.limit) * 100}%` }}
            className={cn(
              "h-full transition-colors first:rounded-l-full",
              dimmed
                ? "bg-muted-foreground/20"
                : profile.managed
                  ? "bg-primary"
                  : "bg-muted-foreground/40",
            )}
          />
        );
      })}
    </div>
  );
}

/**
 * The brands spending the allowance that this app has no Page for.
 *
 * Stated rather than implied. They hold no pool rows, so they can never appear
 * in the table or its chips — but they do spend slots, and that is the half
 * that surprises: an operator counting only what this app shows would read the
 * remaining figure as much larger than it is.
 */
function Unmanaged({ data }: { data: Allowance | null }) {
  if (!data) return null;

  const outside = data.profiles.filter((one) => !one.managed && one.competitors > 0);
  const spentOutside = outside.reduce((total, one) => total + one.competitors, 0);
  const empty = data.profiles.filter((one) => one.competitors === 0).length;

  const parts = [];
  if (spentOutside > 0) {
    parts.push(
      `${spentOutside} on ${outside.length} brand${outside.length === 1 ? "" : "s"} not in this app`,
    );
  }
  if (empty > 0) parts.push(`${empty} brand${empty === 1 ? "" : "s"} watching nobody`);

  return parts.length > 0 ? <>{parts.join(" · ")}</> : null;
}

/** A filter pill. Solid when it is the one in force — the palette has no second
 *  hue to spend on selection, so selection is the inversion. */
function Chip({
  active,
  tone = "default",
  onClick,
  children,
}: {
  active: boolean;
  tone?: "default" | "destructive";
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        "flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[13px] transition-colors",
        active
          ? tone === "destructive"
            // `text-background`, not `text-white`: there is no
            // `--destructive-foreground` in this theme, and dark mode's
            // destructive is a *light* red that white text disappears into.
            ? "border-destructive bg-destructive text-background"
            : "border-primary bg-primary text-primary-foreground"
          : tone === "destructive"
            ? "border-destructive/30 text-destructive hover:bg-destructive/10"
            : "hover:bg-muted",
      )}
    >
      {children}
    </button>
  );
}

/** The count inside a chip. Dimmed against whichever background it lands on, so
 *  the brand name stays the thing you read first. */
function ChipCount({
  active,
  children,
}: {
  active: boolean;
  children: React.ReactNode;
}) {
  return (
    <span className={cn("tabular-nums", active ? "opacity-70" : "text-muted-foreground")}>
      {children}
    </span>
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
        className="h-8 min-w-48 flex-1 text-[13px]"
      />
      <label className="flex items-center gap-1.5 text-[13px] text-muted-foreground">
        under
        <select
          value={target ?? ""}
          onChange={(event) => setUnder(Number(event.target.value))}
          className="h-8 rounded-md border bg-background px-2 text-[13px]"
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
  page,
  onPageChange,
}: {
  rows: CompetitorPage[];
  pages: { id: number; name: string }[];
  page: number;
  onPageChange: (page: number) => void;
}) {
  const nameOf = new Map(pages.map((one) => [one.id, one.name]));

  // Clamped rather than reset: removing the last row of the last page should
  // step back a page, not throw the operator to the top of a 48-row list.
  const totalPages = Math.max(1, Math.ceil(rows.length / POOL_PAGE_SIZE));
  const current = Math.min(page, totalPages);
  const shown = rows.slice((current - 1) * POOL_PAGE_SIZE, current * POOL_PAGE_SIZE);

  return (
    // The rail has its own provider and this screen is not inside it, so the
    // header hint needs one here or Radix throws at render.
    <TooltipProvider>
    <div className="overflow-x-auto">
      {/* Fixed layout. Auto sizing gave the first column every spare pixel, so
          a competitor's name sat a screen's width from the brand beside it and
          the eye had to travel to pair them. */}
      <table className="w-full min-w-184 table-fixed text-[13px]">
        <thead>
          {/* Headings in the text colour, not muted. They name the columns; a
              grey heading over black data reads as the disabled state of a
              table rather than as its structure. */}
          <tr className="border-b text-left font-medium">
            <th className="pb-2">Competitor</th>
            <th className="w-[38%] pb-2">
              Slot in <span className="text-muted-foreground">→</span> Read by
            </th>
            <th className="w-20 pb-2 text-right">
              <HeaderHint
                align="end"
                hint="How many of this competitor's posts are stored from the last syncs. “none” means it is configured but has published nothing we picked up — a dead source looks identical to an unconfigured one everywhere else."
              >
                Posts
              </HeaderHint>
            </th>
            <th className="w-10 pb-2" />
          </tr>
        </thead>
        <tbody className="divide-y">
          {shown.map((row) => (
            // Hover tints the whole row. The four columns are spread across a
            // wide card, and a tint is what carries the eye from a competitor's
            // name to the brand and the count that belong to it.
            <tr
              key={`${row.page_id}-${row.provider_id}`}
              className="group transition-colors hover:bg-muted/40"
            >
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
              <td className="py-2 pr-3">
                <ReadBy row={row} nameOf={nameOf} />
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
        onPageChange={onPageChange}
      />
    </div>
    </TooltipProvider>
  );
}

/**
 * A column heading that explains itself on hover.
 *
 * One heading left needs this: "Posts" counts what was *stored*, not what
 * exists, and "none" is a finding rather than a zero. The two brand columns
 * that used to need one are now a single column that shows the difference
 * instead of describing it. Dotted underline so it reads as explicable rather
 * than as a link.
 */
function HeaderHint({
  hint,
  align = "start",
  children,
}: {
  hint: string;
  align?: "start" | "center" | "end";
  children: React.ReactNode;
}) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span className="cursor-help border-b border-dotted border-muted-foreground/60">
          {children}
        </span>
      </TooltipTrigger>
      <TooltipContent align={align}>{hint}</TooltipContent>
    </Tooltip>
  );
}

/**
 * Which brand pays for this competitor, and which Pages actually read it.
 *
 * Two columns until now — "In brand" and "Read by" — and each needed a tooltip
 * to say how it differed from the other. They are one column here, and the
 * arrow does the explaining: a brand alone means the slot and the reader are
 * the same, `A → B` means B reads what A is paying for. On this account that is
 * 2 rows of 92, so the arrow is the exception the eye can find rather than a
 * shape repeated down the page.
 *
 * Assignment is now the same as reading, which it was not until 2026-09-05: a
 * Page with no assignments of its own read the whole set it was filed under
 * (`routes/sources._visible_to`), so an unassigned competitor was often still
 * being read, and this column carried a third "(default)" state fed by a
 * `reads_by_default` flag to say so. Measured when that was written, 88 of 92
 * rows were unassigned and 44 of those were being read every day.
 *
 * The fallback is gone, so the flag is too, and unassigned now means exactly
 * nobody — which is what the red below has always claimed.
 */
function ReadBy({
  row,
  nameOf,
}: {
  row: CompetitorPage;
  nameOf: Map<number, string>;
}) {
  const assigned = row.assigned_page_ids.map((id) => nameOf.get(id) ?? String(id));

  // Named once when the slot's brand is also the only reader. Printing
  // "History Retraced → History Retraced" down 90 rows is noise that buries the
  // two rows where the arrow means something.
  if (assigned.length === 1 && assigned[0] === row.page_name) {
    return <>{row.page_name}</>;
  }

  if (assigned.length > 0) {
    return (
      <Crosses from={row.page_name}>{assigned.join(", ")}</Crosses>
    );
  }

  // Worth a red: nothing reads this competitor, while it goes on spending one
  // of the hundred. Measured at 44 of 92 when this was written, and fixed by
  // assigning each of them to the brand whose slot they hold.
  return (
    <Crosses from={row.page_name}>
      <span className="text-destructive">nobody</span>
    </Crosses>
  );
}

/** `brand → reader`, for the rows where those differ. Muted on the left because
 *  the reader is the answer; the payer is the context. */
function Crosses({ from, children }: { from: string; children: React.ReactNode }) {
  return (
    <span className="flex items-center gap-1.5">
      <span className="text-muted-foreground">{from}</span>
      <ArrowRight className="size-3 shrink-0 text-muted-foreground/60" />
      {children}
    </span>
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
