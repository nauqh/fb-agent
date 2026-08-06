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
 * A live preview of the Composed Image: the real hero, with the panel drawn
 * here rather than fetched.
 *
 * **This is why editing a highlight shows up instantly.** The hero is the
 * expensive half and it is already on disk; the panel is text on a black
 * rectangle and the browser can lay it out as fast as you type. Compositing on
 * the server is then only about producing the file that gets published, not
 * about seeing what you just changed. The old app worked exactly this way —
 * `<img>` of the hero with `OverlayTextPanelPreview` over it — and this repo
 * lost the behaviour by accident: the component was written before
 * `google-genai` existed, so it had no hero to show and drew a gradient, and
 * once real heroes arrived the callers quietly switched to the baked PNG
 * instead of passing one in.
 *
 * **The panel is an approximation and structurally cannot be anything else.**
 * The real image is measured with fontTools advance widths and rasterised by
 * resvg from Arial-Bold.ttf; the browser is measuring a different font with a
 * different engine, so line breaks and therefore panel height will not match
 * pixel for pixel. What it reproduces faithfully is the form — 4:5, hero on
 * top, solid black panel growing from a 20% floor, highlights in gold,
 * watermark top-right — which is what an edit needs to show.
 *
 * Without `heroSrc` the hero is a CSS gradient, which is the honest rendering
 * of a draft whose picture has not been generated yet.
 */
export function ComposedImage({
  overlayText,
  highlightPhrases,
  watermarkPath,
  heroSrc,
  seed = 0,
  className,
}: {
  overlayText: string | null;
  highlightPhrases: string[];
  /** The generated hero, if one exists. A gradient stands in when it does not. */
  heroSrc?: string | null;
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
        style={
          heroSrc
            ? undefined
            : {
                background: `radial-gradient(120% 90% at 30% 20%, hsl(${hue} 18% 42%), hsl(${(hue + 40) % 360} 22% 14%) 70%), linear-gradient(160deg, hsl(${hue} 25% 30%), hsl(${(hue + 60) % 360} 30% 8%))`,
              }
        }
      >
        {heroSrc ? (
          /* `object-cover` is the compositor's `_cover`: fill the box, crop the
             overflow, centred. The hero is generated at its own resolution near
             the requested ratio, never at exact pixels. */
          // eslint-disable-next-line @next/next/no-img-element
          <img src={heroSrc} alt="" className="absolute inset-0 size-full object-cover" />
        ) : (
          <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_120%,transparent_40%,rgba(0,0,0,0.55))]" />
        )}
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
        // Not `uppercase`: the compositor draws the hook verbatim, and shouting
        // it here made the preview disagree with the PNG beside it.
        className="shrink-0 text-center font-bold leading-[1.26] text-white"
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
