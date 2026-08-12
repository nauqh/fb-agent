"use client";

import type { ReactNode } from "react";
import { MessageCircle, Share2, ThumbsUp } from "lucide-react";

import { PageAvatar } from "@/components/page-badge";

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

function Card({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="overflow-hidden rounded-lg border bg-card">
      <p className="border-b px-4 py-2 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
        {title}
      </p>
      {children}
    </div>
  );
}

export function FacebookPreview({
  pageName,
  avatarPath,
  image,
  caption,
  firstComment,
}: {
  pageName: string;
  avatarPath?: string | null;
  image: ReactNode;
  caption: string;
  firstComment: string;
}) {
  return (
    /* Side by side once there is room. They are read that way — you see the
       post, then you open the comment — and stacking a 1,800-character body
       under the feed card pushed the card off the top of the screen. */
    <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
      <Card title="Feed post">
        <div className="flex items-center gap-2.5 px-4 py-3">
          <PageAvatar name={pageName} avatarPath={avatarPath} size="md" />
          <div className="min-w-0">
            <p className="truncate text-[15px] font-semibold leading-tight">{pageName}</p>
            <p className="text-xs text-muted-foreground">Just now · 🌐</p>
          </div>
        </div>

        {caption.trim() ? (
          <p className="whitespace-pre-wrap px-4 pb-2.5 text-[15px] leading-relaxed">{caption}</p>
        ) : (
          <p className="px-4 pb-2.5 text-[15px] italic text-muted-foreground">No recap yet.</p>
        )}

        {image}

        <div className="flex items-center justify-around border-t px-2 py-1.5 text-sm font-medium text-muted-foreground">
          <span className="flex items-center gap-1.5 px-2 py-1.5">
            <ThumbsUp className="size-4" />
            Like
          </span>
          <span className="flex items-center gap-1.5 px-2 py-1.5">
            <MessageCircle className="size-4" />
            Comment
          </span>
          <span className="flex items-center gap-1.5 px-2 py-1.5">
            <Share2 className="size-4" />
            Share
          </span>
        </div>
      </Card>

      <Card title="First comment">
        {firstComment.trim() ? (
          <div className="flex gap-2.5 px-4 py-4">
            <PageAvatar name={pageName} avatarPath={avatarPath} size="sm" />
            <div className="min-w-0 flex-1">
              <div className="rounded-2xl bg-muted px-3 py-2">
                <p className="text-[13px] font-semibold">{pageName}</p>
                <p className="mt-1 whitespace-pre-wrap text-[15px] leading-relaxed">
                  {firstComment}
                </p>
              </div>
              <p className="mt-1 text-[11px] text-muted-foreground">1 comment · Just now</p>
            </div>
          </div>
        ) : (
          <p className="px-4 py-6 text-[15px] italic text-muted-foreground">No first comment yet.</p>
        )}
      </Card>
    </div>
  );
}
