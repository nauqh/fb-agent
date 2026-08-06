"use client";

import type { ReactNode } from "react";
import { MessageCircle, Share2, ThumbsUp } from "lucide-react";

/**
 * The draft as Facebook will show it: the feed post, then the first comment.
 *
 * Ported in shape from the old repo's `FacebookPostPreview`, with one change
 * that matters. There it was a tab of its own — you left the editor to look at
 * it, so it only ever showed text you had already finished writing. Here it
 * sits beside the fields and re-renders as they change, which is the only
 * reason a preview is worth having.
 *
 * The caption and the first comment are separate cards because they are
 * separate posts. The body is a *comment* the page leaves on its own post —
 * that is the whole format, and a preview that ran them together would hide the
 * one structural thing an operator needs to check.
 */

function Avatar({ name, size = "md" }: { name: string; size?: "sm" | "md" }) {
  const box = size === "sm" ? "size-7" : "size-9";
  return (
    <div
      className={`${box} flex shrink-0 items-center justify-center rounded-full bg-[#1877f2] text-sm font-semibold text-white`}
    >
      {name.slice(0, 1).toUpperCase()}
    </div>
  );
}

function Card({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="overflow-hidden rounded-lg border bg-card">
      <p className="border-b px-3 py-1.5 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
        {title}
      </p>
      {children}
    </div>
  );
}

export function FacebookPreview({
  pageName,
  image,
  caption,
  hashtags,
  firstComment,
}: {
  pageName: string;
  image: ReactNode;
  caption: string;
  hashtags: string[];
  firstComment: string;
}) {
  return (
    /* Side by side once there is room. They are read that way — you see the
       post, then you open the comment — and stacking a 1,800-character body
       under the feed card pushed the card off the top of the screen. */
    <div className="grid items-start gap-4 lg:grid-cols-2">
      <Card title="Feed post">
        <div className="flex items-center gap-2 px-3 py-2.5">
          <Avatar name={pageName} />
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold leading-tight">{pageName}</p>
            <p className="text-[11px] text-muted-foreground">Just now · 🌐</p>
          </div>
        </div>

        {caption.trim() ? (
          <p className="whitespace-pre-wrap px-3 pb-2 text-sm leading-relaxed">{caption}</p>
        ) : (
          <p className="px-3 pb-2 text-sm italic text-muted-foreground">No recap yet.</p>
        )}

        {hashtags.length > 0 ? (
          <p className="px-3 pb-2.5 text-sm leading-relaxed text-[#1877f2]">
            {hashtags.join(" ")}
          </p>
        ) : null}

        {image}

        <div className="flex items-center justify-around border-t px-2 py-1 text-xs font-medium text-muted-foreground">
          <span className="flex items-center gap-1.5 px-2 py-1.5">
            <ThumbsUp className="size-3.5" />
            Like
          </span>
          <span className="flex items-center gap-1.5 px-2 py-1.5">
            <MessageCircle className="size-3.5" />
            Comment
          </span>
          <span className="flex items-center gap-1.5 px-2 py-1.5">
            <Share2 className="size-3.5" />
            Share
          </span>
        </div>
      </Card>

      <Card title="First comment">
        {firstComment.trim() ? (
          <div className="flex gap-2 px-3 py-3">
            <Avatar name={pageName} size="sm" />
            <div className="min-w-0 flex-1">
              <div className="rounded-2xl bg-muted px-3 py-2">
                <p className="text-xs font-semibold">{pageName}</p>
                <p className="mt-0.5 whitespace-pre-wrap text-sm leading-relaxed">
                  {firstComment}
                </p>
              </div>
              <p className="mt-1 text-[11px] text-muted-foreground">1 comment · Just now</p>
            </div>
          </div>
        ) : (
          <p className="px-3 py-5 text-sm italic text-muted-foreground">No first comment yet.</p>
        )}
      </Card>
    </div>
  );
}
