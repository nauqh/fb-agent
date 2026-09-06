"use client";

import { useEffect, useState } from "react";
import { AlertTriangle } from "lucide-react";

import { cn } from "@/lib/utils";

/**
 * The frame Settings and Global are both built in: a rail of sections, and one
 * section at a time in the pane beside it.
 *
 * They were a two-column grid of cards, and the grid was the problem. The cards
 * are wildly unequal — Feeds is six rows, Identity is three lines, Prompts is
 * three 10-row textareas — so every row of the grid was as tall as its taller
 * card and the shorter one sat in ~200px of white. Measured on History
 * Retraced at 1600px: Settings ran 2,400px with roughly a third of it empty.
 *
 * A rail fixes that by not showing the other five sections at all, which is
 * also the honest reading of what these screens are for. Nobody edits feeds and
 * prompt text in the same sitting; they come here to change one thing.
 *
 * The rail is not just navigation — it is the **status column**. Each section
 * carries its own count, and a section that is unconfigured says so *in the
 * rail*, so the thing you cannot see from here is never a surprise. That is why
 * `gap` exists and why it is styled loudly.
 *
 * A rail lists only sections of the screen it is on. The two screens briefly
 * cross-linked — Settings' rail naming Global's sections and back — and that is
 * gone: a rail entry that navigates away is indistinguishable from one that
 * switches panes until it has already moved you. Settings is one Page, Global is
 * the account, and the rail on each stays inside its own scope.
 */
export type ConfigSection = {
  /** Also the URL hash, so a section can be linked to and survives a reload. */
  id: string;
  label: string;
  /**
   * The count or figure that describes this section, right-aligned.
   *
   * `PENDING` while the query behind it is in flight. Undefined means this
   * section has no figure at all — a different fact, and the rail has to render
   * them differently: a blank where a number is coming reads as "nothing here",
   * which is exactly the wrong answer for the column whose job is to report on
   * sections you cannot see.
   */
  meta?: React.ReactNode;
  /**
   * Something here is unset, and it stops something else from working. Renders
   * as a warning triangle in the rail; the section itself should explain.
   */
  gap?: boolean;
  /** The pane this section shows. */
  body: React.ReactNode;
};

export type ConfigGroup = {
  label: string;
  sections: ConfigSection[];
};

export function ConfigShell({
  groups,
  header,
}: {
  groups: ConfigGroup[];
  header: React.ReactNode;
}) {
  const local = groups.flatMap((group) => group.sections);
  const [active, setActive] = useState(local[0]?.id ?? "");

  // The hash is read after mount, never during render: the server has no
  // `location`, and seeding state from it would hydrate to a different section
  // than it rendered. `hashchange` covers a link to a section of the screen you
  // are already on, which no re-render would otherwise notice.
  useEffect(() => {
    const fromHash = () => {
      const wanted = window.location.hash.slice(1);
      if (wanted && local.some((section) => section.id === wanted)) setActive(wanted);
    };
    fromHash();
    window.addEventListener("hashchange", fromHash);
    return () => window.removeEventListener("hashchange", fromHash);
    // `local` is rebuilt every render; its *ids* are what matter and they are
    // static per screen, so this deliberately runs once.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function open(id: string) {
    setActive(id);
    // `replaceState`, not `push`: flipping between six sections should not fill
    // the back button with a trail nobody wants to walk.
    window.history.replaceState(null, "", `#${id}`);
  }

  const shown = local.find((section) => section.id === active) ?? local[0];

  return (
    // **One scroller, and it is the row — not the rail and not the screen.**
    //
    // Three arrangements have been tried here and each failed differently:
    //
    // - rail and pane each with their own `overflow-y-auto` inside an
    //   `overflow-hidden` shell. Two scrollers side by side, so reaching the
    //   bottom of Prompts depended on which column the pointer was over;
    // - the whole screen scrolling. The bottom was reachable, but the rail —
    //   which is the status column, and the only place a gap in an unopened
    //   section is visible — scrolled away with it;
    // - this one. The header is outside the scroller so it never moves, the row
    //   below owns the scroll, and the rail is `sticky` within it. The rail
    //   holds still, the pane scrolls under it, and a pane is as tall as it
    //   needs to be.
    <div className="flex w-full flex-col pb-16 lg:min-h-0 lg:flex-1 lg:overflow-hidden lg:pb-0">
      {header}

      {/* Below `lg` the rail is a horizontal strip: a 200px column beside a form
          on a phone leaves neither enough room. */}
      <div className="flex flex-col gap-5 lg:min-h-0 lg:flex-1 lg:flex-row lg:gap-6 lg:overflow-y-auto lg:pr-3">
        {/* `self-start` is what makes `sticky` work: a stretched flex item is
            already as tall as the row it is in, so it has nothing to stick
            within and would scroll away with the pane. */}
        <nav
          data-config-rail
          className="shrink-0 lg:sticky lg:top-0 lg:w-52 lg:self-start lg:pb-10"
        >
          <div className="flex gap-1 overflow-x-auto lg:block lg:space-y-6 lg:overflow-visible">
            {groups.map((group) => (
              <div key={group.label} className="flex shrink-0 gap-1 lg:block lg:space-y-0.5">
                <p className="hidden px-2 pb-1.5 font-mono text-[11px] font-medium tracking-[0.12em] text-muted-foreground uppercase lg:block">
                  {group.label}
                </p>
                {group.sections.map((section) => (
                  <button
                    key={section.id}
                    type="button"
                    onClick={() => open(section.id)}
                    aria-current={section.id === shown?.id ? "page" : undefined}
                    className={cn(
                      // The press is on pointer-*down*, which is the whole
                      // point: feedback that waits for the click has already
                      // lost the feeling of directness. 100ms and a hair under
                      // 1.0 — enough to feel, not enough to notice.
                      "group flex shrink-0 items-center gap-2 rounded-md px-2.5 py-1.5 text-[13px] whitespace-nowrap transition-[transform,background-color,color] duration-100 active:scale-[0.98] lg:w-full",
                      section.id === shown?.id
                        ? "bg-accent font-medium text-foreground"
                        : "text-muted-foreground hover:bg-accent/60 hover:text-foreground",
                    )}
                  >
                    <RailLabel section={section} />
                  </button>
                ))}
              </div>
            ))}
          </div>
        </nav>

        {/* No scroller of its own: the pane is as tall as its section, and the
            row around it does the scrolling. */}
        <div className="min-w-0 flex-1 lg:pb-16">
          {shown?.body}
        </div>
      </div>
    </div>
  );
}

/**
 * Stand-in for a figure that has not arrived yet.
 *
 * Measured before this existed: on first paint the rail showed Feeds, Prompts
 * and Competitors with no figure at all, for as long as their queries took —
 * three sections reporting nothing, on the column that exists to report. An
 * en dash at the same width as a one- or two-digit count also stops the row
 * reflowing when the number lands.
 */
export const PENDING = <span aria-hidden>&ndash;</span>;

function RailLabel({ section }: { section: ConfigSection }) {
  return (
    <>
      <span className="min-w-0 flex-1 truncate text-left">{section.label}</span>
      {section.gap ? (
        <AlertTriangle className="size-3 shrink-0 text-destructive" />
      ) : section.meta !== undefined ? (
        <span className="shrink-0 tabular-nums text-muted-foreground">
          {section.meta}
        </span>
      ) : null}
    </>
  );
}

/**
 * One section in the pane: its title, what it is for, and its figure.
 *
 * The figure goes top-right rather than under the title — pushing the number to
 * the edge is what lets the eye read six sections' worth of counts down one
 * line, and it is the one thing about a card that a title never tells you.
 */
export function Pane({
  title,
  hint,
  meta,
  action,
  children,
}: {
  title: string;
  hint?: React.ReactNode;
  meta?: React.ReactNode;
  action?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-2xl border bg-card">
      <div className="flex items-start justify-between gap-6 border-b px-5 py-4">
        <div className="min-w-0">
          <h2 className="text-base font-semibold tracking-tight">{title}</h2>
          {hint ? (
            <p className="max-w-prose pt-1 text-[13px] text-muted-foreground">{hint}</p>
          ) : null}
        </div>
        <div className="flex shrink-0 items-center gap-3">
          {meta !== undefined ? (
            <span className="text-[13px] whitespace-nowrap tabular-nums text-muted-foreground">
              {meta}
            </span>
          ) : null}
          {action}
        </div>
      </div>
      <div className="p-5">{children}</div>
    </section>
  );
}

/** A sub-heading inside a pane. Uppercase micro-label, hairline rule. */
export function Block({
  label,
  children,
  className,
}: {
  label: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={className}>
      <p className="pb-3 font-mono text-[11px] font-medium tracking-[0.12em] text-muted-foreground uppercase">
        {label}
      </p>
      {children}
    </div>
  );
}

/**
 * Something is not set, and here is what that stops.
 *
 * Deliberately not the muted dashed box an empty list usually gets. Every gap
 * this renders has a consequence somewhere else in the app — no publishing
 * times means "Schedule next available" answers 409, no watermark means a
 * composite with nothing to stamp — and a grey sentence is how those went
 * unnoticed long enough to be reported as bugs. The rail carries a triangle
 * for the same reason: from the rail you cannot see the section at all.
 */
export function Gap({
  title,
  children,
}: {
  title: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="flex items-start gap-3 rounded-md border border-destructive/30 bg-destructive/[0.04] px-4 py-3">
      <AlertTriangle className="mt-0.5 size-3.5 shrink-0 text-destructive" />
      <div className="min-w-0 space-y-1">
        <p className="text-[13px] font-medium">{title}</p>
        {children ? (
          <p className="text-[13px] text-muted-foreground">{children}</p>
        ) : null}
      </div>
    </div>
  );
}
