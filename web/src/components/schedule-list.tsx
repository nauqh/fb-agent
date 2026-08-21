"use client";

import { useState } from "react";
import { ExternalLink, MessageSquareText } from "lucide-react";

import { Empty } from "@/components/screen";
import { StatusPill, type StatusTone } from "@/components/status-pill";
import { pageToday } from "@/lib/format";
import type { ScheduledPost } from "@/lib/types";

/**
 * The reading view: what each post actually says.
 *
 * The week grid answers "which slot is empty". This answers "what went out",
 * and the first version answered it badly — a fixed 48px thumbnail that is
 * permanently blank for every historical post (their image links expire two
 * hours after publish), beside two truncated lines of a 720-character caption
 * that begins with a title and continues as emoji bullet points.
 *
 * Metricool stores the caption as one string, but it is not unstructured: line
 * one is the title, the blank-line-separated paragraphs after it are the recap
 * points, and the hashtags sit at the end. Parsing that back out is what makes
 * a row scannable — the title alone identifies a post far better than the first
 * ninety characters of its opening bullet.
 */
export function ScheduleList({ posts }: { posts: ScheduledPost[] }) {
  if (!posts.length) {
    return <Empty>Nothing scheduled in this window.</Empty>;
  }

  const days = groupByDay(posts);
  // The daily rhythm, from the data rather than a constant: this page runs
  // 9-10 posts a day, so a day with 7 is worth pointing at. The median is
  // robust against the part-finished day at either end of the window.
  const typical = median(days.map(([, rows]) => rows.length));

  return (
    <div className="space-y-6 pb-10">
      {days.map(([day, rows]) => (
        <section key={day} className="space-y-2">
          <h2 className="sticky top-0 z-10 flex items-baseline gap-2 bg-background/90 py-1 backdrop-blur">
            <span className="font-mono text-[11px] font-medium uppercase tracking-[0.12em] text-muted-foreground">
              {dayLabel(day)}
            </span>
            <span className="font-mono text-[11px] tabular-nums text-muted-foreground">
              {rows.length} post{rows.length === 1 ? "" : "s"}
            </span>
            {rows.length < typical ? (
              <span className="font-mono text-[11px] text-amber-600 dark:text-amber-500">
                {typical - rows.length} below the usual {typical}
              </span>
            ) : null}
          </h2>

          <div className="divide-y overflow-hidden rounded-2xl border">
            {rows.map((post) => (
              <Row key={post.id} post={post} />
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}

function Row({ post }: { post: ScheduledPost }) {
  const { title, points, tags } = parse(post.text);
  const [open, setOpen] = useState(false);

  return (
    <div className="flex gap-4 px-4 py-3">
      <div className="w-12 shrink-0 pt-0.5 font-mono text-[11px] tabular-nums text-muted-foreground">
        {post.published_at.slice(11, 16)}
      </div>

      <Thumb src={post.image_url} />

      <div className="min-w-0 flex-1 space-y-1.5">
        <div className="flex items-start gap-2">
          <p className="min-w-0 flex-1 text-sm font-medium leading-snug">
            {title || <span className="text-muted-foreground">No caption</span>}
          </p>
          <PostStatus status={post.status} />
        </div>

        {points.length ? (
          <ul className="space-y-0.5 text-xs leading-relaxed text-muted-foreground">
            {(open ? points : points.slice(0, 2)).map((point, index) => (
              <li key={index} className={open ? undefined : "truncate"}>
                {point}
              </li>
            ))}
          </ul>
        ) : null}

        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-[11px] text-muted-foreground">
          {points.length > 2 ? (
            <button
              type="button"
              onClick={() => setOpen((was) => !was)}
              className="hover:text-foreground"
            >
              {open ? "Show less" : `+${points.length - 2} more`}
            </button>
          ) : null}

          {post.first_comment ? (
            // Whether the body actually went out with it. The first comment is
            // where the story lives, and Metricool posts it separately — a post
            // that lost it is a post with a recap and no article.
            <span className="inline-flex items-center gap-1" title={post.first_comment}>
              <MessageSquareText className="size-3" />
              {post.first_comment.length.toLocaleString()} char comment
            </span>
          ) : (
            <span className="text-amber-600 dark:text-amber-500">No first comment</span>
          )}

          {post.draft_id ? (
            <span className="rounded border border-gold/40 bg-gold/10 px-1.5 py-0.5 text-foreground">
              fb-agent · draft {post.draft_id}
            </span>
          ) : null}

          {post.public_url ? (
            <a
              href={post.public_url}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1 hover:text-foreground"
            >
              <ExternalLink className="size-3" />
              View
            </a>
          ) : null}

          {tags.length ? (
            <span className="truncate font-mono opacity-70">{tags.join(" ")}</span>
          ) : null}
        </div>
      </div>
    </div>
  );
}

/**
 * The caption, split back into the shape the writer produced.
 *
 * Title on line one, recap points as the paragraphs after it, hashtags last.
 * Anything that does not fit that shape still renders — an unrecognised caption
 * becomes its own title and no points, which is the honest degradation.
 */
function parse(text: string): { title: string; points: string[]; tags: string[] } {
  const lines = text
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);

  if (!lines.length) return { title: "", points: [], tags: [] };

  const tags = lines.filter((line) => /^#\S+(\s+#\S+)*$/.test(line));
  const body = lines.filter((line) => !tags.includes(line));

  return {
    title: body[0] ?? "",
    points: body.slice(1),
    tags: tags.flatMap((line) => line.split(/\s+/)),
  };
}

/**
 * Shown only when there is actually a picture to show.
 *
 * Every historical post here has a dead image link — the old system signed them
 * with `publishAt + 2h` expiry, and 0 of 105 in a fortnight's window still
 * resolve. A placeholder icon on every single row is noise pretending to be
 * information, so a failed load collapses the space instead.
 */
function Thumb({ src }: { src: string | null }) {
  const [broken, setBroken] = useState(false);

  if (!src || broken) return null;

  return (
    <div className="aspect-square w-12 shrink-0 overflow-hidden rounded-2xl border bg-muted">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={src}
        alt=""
        className="size-full object-cover"
        onError={() => setBroken(true)}
      />
    </div>
  );
}

/** Metricool's own words for a planner row, mapped onto the shared pill. */
const STATUS: Record<string, { label: string; tone: StatusTone }> = {
  PUBLISHED: { label: "Published", tone: "positive" },
  ERROR: { label: "Error", tone: "negative" },
  DRAFT: { label: "Draft", tone: "neutral" },
};

function PostStatus({ status }: { status: string }) {
  // Unknown statuses keep Metricool's raw word rather than inventing one.
  const { label, tone } = STATUS[status] ?? { label: status, tone: "neutral" as const };
  return <StatusPill tone={tone} label={label} />;
}

/** Keyed by the date part of the naive local stamp — no timezone maths. */
function groupByDay(posts: ScheduledPost[]): [string, ScheduledPost[]][] {
  const days = new Map<string, ScheduledPost[]>();
  for (const post of posts) {
    const day = post.published_at.slice(0, 10);
    const rows = days.get(day);
    if (rows) rows.push(post);
    else days.set(day, [post]);
  }
  return [...days.entries()];
}

function median(counts: number[]): number {
  if (!counts.length) return 0;
  const sorted = [...counts].sort((a, b) => a - b);
  return sorted[Math.floor(sorted.length / 2)];
}

function dayLabel(day: string): string {
  // `day` came off a planner stamp, which is naive local time in the Page's
  // zone. Comparing it against the browser's date labelled the wrong row
  // "Today" for the three hours a day the two calendars disagree.
  if (day === pageToday()) return `Today · ${day}`;
  return new Date(`${day}T12:00:00`).toLocaleDateString(undefined, {
    weekday: "long",
    day: "numeric",
    month: "short",
  });
}
