/**
 * What the renderer is configured with.
 *
 * Settings used to read `LAYOUT` from `lib/fixtures/pages.ts` — a hand-kept
 * copy of `layout.yml` on this side of the wire. So a screen whose whole job is
 * to show what the compositor uses was showing something that could disagree
 * with it, silently, the moment either file was edited alone.
 *
 * The fixture stays for `ComposedImage`, which needs geometry synchronously on
 * every keystroke and is an approximation anyway. Settings shows the server's
 * answer, so a drift between the two is visible there rather than invisible
 * everywhere.
 */

import { get } from "@/lib/api/client";

export interface Layout {
  image: { width: number; height: number; edge_margin_ratio: number };
  panel: { ratio: number; max_ratio: number; color: string; opacity: number };
  text: {
    font_size_px: number;
    line_height_ratio: number;
    align: string;
    color: string;
    padding: { left_px: number; right_px: number; top_px: number; bottom_px: number };
  };
  highlight: { color: string };
  watermark: { max_px: number; top_ratio: number };
  font: { family: string; weight: string; path: string };
}

export async function getLayout(): Promise<Layout> {
  return get<Layout>("/layout");
}
