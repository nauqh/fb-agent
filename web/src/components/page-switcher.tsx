"use client";

import { Check, ChevronDown } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { pageAvatar } from "@/lib/page-avatar";
import { usePageScope } from "@/lib/page-scope";
import { cn } from "@/lib/utils";

/**
 * Which Page the screen is showing. Every screen, from one place.
 *
 * Rendered by `ScreenHeader` rather than added to each screen by hand, so a
 * screen cannot be written that quietly ignores the choice.
 *
 * A dropdown rather than a row of tabs, which is what the old app used
 * (`facebook-page-single-select.tsx`) and is the shape that survives growth:
 * this is a *scope* control, not navigation between peers, and it sits beside
 * each screen's own tabs — Competitors/Tweets/RSS on Sources, Week/List on
 * Schedule — where a second tab strip reads as another set of them. It also
 * costs one control's width at ten Pages as it does at two, which the tabs did
 * not.
 *
 * Hidden entirely below two Pages: a switch with a single position is
 * decoration, and it was the *four-brand* version of this control whose
 * hardcoded constant ADR-0003 destroyed. Pages are rows, so this appears the
 * moment a second one is inserted and disappears if it is deleted.
 *
 * The mark is `rounded-sm`, not the circle `PageAvatar` draws. Facebook crops
 * a page's picture round and the badge follows it, but here the mark is a
 * 20px control affordance rather than an identity beside a name — and The Fact
 * Feed's is a square wordmark whose corners a circular crop eats.
 */
export function PageSwitcher() {
  const { pages, page, select } = usePageScope();

  if (pages.length < 2 || !page) return null;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        {/* `h-8` and `text-xs`: the header's own title is the thing to read
            first, and this sits next to it saying which Page that title is
            about. */}
        <Button
          variant="outline"
          size="sm"
          className="h-8 gap-2 pr-2 pl-2 text-xs font-medium"
        >
          <Mark page={page} />
          <span className="max-w-40 truncate">{page.name}</span>
          <ChevronDown className="size-3.5 shrink-0 text-muted-foreground" />
        </Button>
      </DropdownMenuTrigger>

      <DropdownMenuContent align="end" className="min-w-52">
        {pages.map((candidate) => {
          const active = candidate.id === page.id;
          return (
            <DropdownMenuItem
              key={candidate.id}
              onSelect={() => select(candidate.id)}
              className="gap-2"
            >
              <Mark page={candidate} />
              <span className="min-w-0 flex-1 truncate">{candidate.name}</span>
              {/* The tick occupies its slot whether or not it is drawn, so the
                  names stay on one left edge instead of shifting by 16px as
                  the selection moves. */}
              <Check
                className={cn("size-3.5 shrink-0", !active && "invisible")}
                aria-hidden={!active}
              />
            </DropdownMenuItem>
          );
        })}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function Mark({
  page,
}: {
  page: { name: string; avatar_image_path?: string | null; avatar_url?: string | null };
}) {
  const src = pageAvatar(page);
  if (src) {
    return (
      // A committed asset at a fixed 20px, not a content image.
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={src}
        alt=""
        className="size-5 shrink-0 rounded-sm bg-white object-contain"
      />
    );
  }

  return (
    <span className="flex size-5 shrink-0 items-center justify-center rounded-sm bg-[#1877f2] text-[10px] font-semibold text-white">
      {page.name.slice(0, 1).toUpperCase()}
    </span>
  );
}
