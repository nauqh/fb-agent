"use client";

import { useMemo } from "react";

import { LAYOUT } from "@/lib/fixtures/pages";
import { cn } from "@/lib/utils";

/**
 * The committed watermark, copied to `public/` for the preview only.
 *
 * The API composites from `api/assets/watermarks/history-retraced.png`; the
 * browser cannot read that path, and re-drawing the wordmark in SVG would be a
 * second version of a logo that already exists. This copy goes away the moment
 * the preview is replaced by the composed PNG the API actually serves.
 */
const WATERMARK_PREVIEW = "/watermarks/history-retraced.png";

/**
 * A preview of the Composed Image.
 *
 * **This is an approximation, and structurally cannot be anything else.** The
 * real image is measured with fontTools advance widths and rasterised by resvg
 * from Arial-Bold.ttf; the browser here is measuring a different font with a
 * different engine, so line breaks and therefore panel height will not match
 * pixel for pixel. What it does reproduce faithfully is the *form* — 4:5, hero
 * on top, solid black panel below that grows to fit the copy from a 20% floor,
 * highlight phrases in gold, watermark top-right of the hero — and it re-lays
 * live as the operator edits, which is the thing worth looking at.
 *
 * The hero is a CSS gradient. No `google-genai` exists yet, and a checked-in
 * photograph would imply one does.
 */
export function ComposedImage({
  overlayText,
  highlightPhrases,
  watermarkPath,
  seed = 0,
  className,
}: {
  overlayText: string | null;
  highlightPhrases: string[];
  /**
   * `page.watermark_image_path`, relative to `API_DIR`. Null is not a fallback:
   * the asset is committed at `api/assets/watermarks/`, so a Page without one is
   * a broken Page and this says so instead of quietly printing the name.
   */
  watermarkPath: string | null;
  /** Varies the hero gradient so two drafts do not look identical. */
  seed?: number;
  className?: string;
}) {
  const segments = useMemo(
    () => splitOnHighlights(overlayText ?? "", highlightPhrases),
    [overlayText, highlightPhrases],
  );

  const hue = (seed * 47) % 360;

  return (
    <div
      className={cn(
        // Container query unit `cqw` is what keeps the type scaling with the
        // card instead of the viewport — the panel must look the same in the
        // 180px list thumbnail and the 380px detail view.
        "@container flex flex-col overflow-hidden rounded-md border bg-black",
        className,
      )}
      style={{ aspectRatio: `${LAYOUT.width} / ${LAYOUT.height}` }}
    >
      {/* Hero. Shrinks as the panel grows, exactly as the compositor does. */}
      <div
        className="relative min-h-0 flex-1"
        style={{
          background: `radial-gradient(120% 90% at 30% 20%, hsl(${hue} 18% 42%), hsl(${(hue + 40) % 360} 22% 14%) 70%), linear-gradient(160deg, hsl(${hue} 25% 30%), hsl(${(hue + 60) % 360} 30% 8%))`,
        }}
      >
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_120%,transparent_40%,rgba(0,0,0,0.55))]" />
        {/* Watermark: top-right of the hero, inset by edge_margin_ratio,
            natural aspect, capped at 0.22 × width. */}
        <div
          className="absolute"
          style={{
            top: `${LAYOUT.edgeMarginRatio * 100}%`,
            right: `${LAYOUT.edgeMarginRatio * 100}%`,
            width: `${(LAYOUT.watermarkMaxPx / LAYOUT.width) * 100}%`,
          }}
        >
          {watermarkPath ? (
            // A fixed asset at a container-relative width; next/image would add
            // a loader and an intrinsic size for nothing here.
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={WATERMARK_PREVIEW}
              alt=""
              className="w-full drop-shadow"
            />
          ) : (
            <p className="rounded border border-red-500/70 bg-black/70 px-1 py-0.5 text-right text-[8px] leading-tight text-red-400">
              no watermark asset
            </p>
          )}
        </div>
      </div>

      {/* Panel. `min-height` is the 20% floor; the content pushes it taller. */}
      <div
        className="shrink-0 text-center font-bold uppercase leading-[1.26] text-white"
        style={{
          minHeight: `${LAYOUT.panelRatio * 100}%`,
          maxHeight: `${LAYOUT.panelMaxRatio * 100}%`,
          backgroundColor: LAYOUT.panelColor,
          padding: "6% 4%",
          fontSize: "clamp(10px, 4.1cqw, 19px)",
        }}
      >
        {segments.length === 0 ? (
          <span className="text-white/25">No overlay text</span>
        ) : (
          segments.map((segment, index) => (
            <span
              key={index}
              style={segment.highlight ? { color: LAYOUT.highlightColor } : undefined}
            >
              {segment.text}
            </span>
          ))
        )}
      </div>
    </div>
  );
}

interface Segment {
  text: string;
  highlight: boolean;
}

/**
 * Split the panel text on its Highlight Phrases.
 *
 * A Highlight Phrase is defined as an *exact substring* of the panel text,
 * copied verbatim by the writer. Anything that does not literally appear is
 * dropped rather than fuzzily matched — the same silence the compositor gives
 * it, so a bad phrase is visible here as a missing gold word rather than
 * papered over.
 */
export function splitOnHighlights(text: string, phrases: string[]): Segment[] {
  if (!text) return [];

  const present = phrases
    .filter((phrase) => phrase && text.includes(phrase))
    // Longest first, so a phrase contained inside another does not win.
    .sort((a, b) => b.length - a.length);

  if (present.length === 0) return [{ text, highlight: false }];

  const marked = new Array<boolean>(text.length).fill(false);
  for (const phrase of present) {
    let from = text.indexOf(phrase);
    while (from !== -1) {
      for (let i = from; i < from + phrase.length; i++) marked[i] = true;
      from = text.indexOf(phrase, from + phrase.length);
    }
  }

  const segments: Segment[] = [];
  let start = 0;
  for (let i = 1; i <= text.length; i++) {
    if (i === text.length || marked[i] !== marked[start]) {
      segments.push({ text: text.slice(start, i), highlight: marked[start] });
      start = i;
    }
  }
  return segments;
}
