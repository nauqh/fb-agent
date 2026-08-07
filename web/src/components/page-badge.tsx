"use client";

import { cn } from "@/lib/utils";

/**
 * A Page, as Facebook shows it: round mark, then the name.
 *
 * `page.avatar_image_path` is the wordmark on white, which is what Facebook
 * shows beside the name and what the old app drew here. The *watermark* is not
 * a substitute for it — that is the same wordmark in white ink for stamping
 * onto a photograph, and a circular crop of it is a fragment of a word on a
 * black disc.
 *
 * The initial on Facebook blue is the fallback for a Page with no avatar set.
 *
 * Shared with the feed preview so the two cannot drift into different ideas of
 * what a Page looks like.
 */
export function PageBadge({
  name,
  avatarPath,
  size = "sm",
  className,
}: {
  name: string;
  avatarPath?: string | null;
  size?: "sm" | "md";
  className?: string;
}) {
  return (
    <div className={cn("flex min-w-0 items-center gap-2", className)}>
      <PageAvatar name={name} avatarPath={avatarPath} size={size} />
      <span className="truncate">{name}</span>
    </div>
  );
}

export function PageAvatar({
  name,
  avatarPath,
  size = "sm",
}: {
  name: string;
  avatarPath?: string | null;
  size?: "sm" | "md";
}) {
  // Bigger than a favicon: the mark is a two-line wordmark, so at 24px the
  // second line is a smudge.
  const box = size === "sm" ? "size-9" : "size-11";

  if (avatarPath) {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={`/api/${avatarPath}`}
        alt=""
        className={cn(box, "shrink-0 rounded-full border bg-white object-contain")}
      />
    );
  }

  return (
    <div
      className={cn(
        box,
        "flex shrink-0 items-center justify-center rounded-full bg-[#1877f2] font-semibold text-white",
        size === "sm" ? "text-sm" : "text-base",
      )}
    >
      {name.slice(0, 1).toUpperCase()}
    </div>
  );
}
