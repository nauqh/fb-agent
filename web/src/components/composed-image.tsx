"use client";

import { useMemo } from "react";

import type { ResolvedLayout } from "@/lib/api/layout";
import { watermarkUrl } from "@/lib/api/pages";
import type { Page } from "@/lib/types";
import { cn } from "@/lib/utils";

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
 * **Every value comes from the Page's resolved layout.** It used to come from
 * `LAYOUT` in `lib/fixtures/pages.ts`, a hand-kept copy of `layout.yml` with no
 * per-Page anything in it — and the panel's own padding and type size were not
 * even that, but two literals (`padding: "6% 4%"`, `clamp(10px, 4.1cqw, 19px)`)
 * that happened to look about right. So the four padding sliders and the text
 * size on Global moved the card on Global and moved nothing on the screen the
 * operator actually works on. Reported by the client as "padding doesn't seem
 * to be working anymore"; the write path was fine the whole time.
 *
 * The reason given for the fixture was that this component "needs geometry
 * synchronously on every keystroke". That was answering the wrong question: a
 * layout changes per *Page*, not per keystroke, so one fetch held in state is
 * synchronous for every render that follows it.
 *
 * **The panel is an approximation and structurally cannot be anything else.**
 * The real image is measured with fontTools advance widths and rasterised by
 * resvg from Arial-Bold.ttf; the browser is measuring a different font with a
 * different engine, so line breaks and therefore panel height will not match
 * pixel for pixel. What it reproduces faithfully is the form, and it now
 * reproduces the *Page's* form rather than History Retraced's.
 *
 * Without `heroSrc` the hero is a CSS gradient, which is the honest rendering
 * of a draft whose picture has not been generated yet.
 */
export function ComposedImage({
  layout,
  page,
  overlayText,
  highlightPhrases,
  heroSrc,
  insetSrc,
  insetSizePx,
  insetXRatio,
  insetYRatio,
  insetBorderWidthPx,
  insetBorderColor,
  seed = 0,
  className,
}: {
  /**
   * The Page's resolved layout — `layout.yml` with that Page's overrides laid
   * over it, exactly what `layout_for.resolve` hands the compositor. Required
   * rather than defaulted: a default here is a second copy of the file, which
   * is the thing that drifted.
   */
  layout: ResolvedLayout;
  /**
   * The Page, for the three things the layout does not carry: whether it stamps
   * a mark at all, which mark, and the headline chip's word.
   */
  page: Page;
  overlayText: string | null;
  highlightPhrases: string[];
  /** The generated hero, if one exists. A gradient stands in when it does not. */
  heroSrc?: string | null;
  /**
   * The uploaded circular inset. Absent is the normal case: no upload, no
   * circle, and nothing stands in for it.
   */
  insetSrc?: string | null;
  /** Its diameter in card pixels. Undefined takes the layout's default. */
  insetSizePx?: number | null;
  /**
   * Its centre as fractions of the card. Null on either axis means the default
   * for that axis, which is the seam — and the seam is a flexbox edge here, not
   * a number, so a defaulted disc is rendered inside the hero and a placed one
   * against the card.
   */
  insetXRatio?: number | null;
  insetYRatio?: number | null;
  /**
   * The draft's own ring. Null on either takes the Page's layout — and null is
   * not `0`: `0` is a draft that has chosen to have no ring.
   */
  insetBorderWidthPx?: number | null;
  insetBorderColor?: string | null;
  /** Varies the hero gradient so two drafts do not look identical. */
  seed?: number;
  className?: string;
}) {
  const segments = useMemo(
    () => splitOnHighlights(overlayText ?? "", highlightPhrases),
    [overlayText, highlightPhrases],
  );

  const hue = (seed * 47) % 360;
  const full = layout.template === "full_overlay";

  /** A card pixel as a percentage of the card's width. */
  const scale = (px: number) => `${(px / layout.image.width) * 100}%`;

  /**
   * The disc, and the two places it can live.
   *
   * `inset_y_ratio` null means the seam, and the seam is a flexbox edge rather
   * than a number here — the panel sizes itself to its text, so nothing in this
   * component knows where it falls. So a defaulted disc renders *inside* the
   * hero, where `bottom-0` is the seam by construction, and a placed one renders
   * against the card at a percentage. Same split per axis as `inset_centre` on
   * the server, so a half-set position looks the same in both.
   */
  // `??`, never `||` — `0` is a real choice here ("no ring") and `||` would
  // send it back to the Page's width, which is the one value it is trying not
  // to be.
  const border = Math.max(
    0,
    insetBorderWidthPx ?? layout.portrait.border_width_px,
  );
  const borderColor = insetBorderColor ?? layout.portrait.border_color;
  const width = clampInset(insetSizePx, layout) + border * 2;
  const disc = insetSrc ? (
    <div
      className="absolute z-10 aspect-square rounded-full"
      style={{
        width: scale(width),
        // Zero border width is a legitimate setting — "no border" is the
        // client's own first option — and it has to render as a disc with no
        // ring rather than as a hairline, so the padding is scaled from the
        // value rather than assumed to be non-zero.
        backgroundColor: borderColor,
        padding: scale(border),
        ...(insetXRatio == null
          ? { right: `${layout.image.edge_margin_ratio * 100}%` }
          : { left: `${insetXRatio * 100}%`, translate: "-50%" }),
        ...(insetYRatio == null
          ? { bottom: 0, translate: `${insetXRatio == null ? "0" : "-50%"} 50%` }
          : { top: `${insetYRatio * 100}%`, translate: `${insetXRatio == null ? "0" : "-50%"} -50%` }),
      }}
    >
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={insetSrc} alt="" className="size-full rounded-full object-cover" />
    </div>
  ) : null;

  const heroImage = heroSrc ? (
    /* `object-cover` is the compositor's `_cover`: fill the box, crop the
       overflow, centred. The hero is generated at its own resolution near
       the requested ratio, never at exact pixels. */
    // eslint-disable-next-line @next/next/no-img-element
    <img src={heroSrc} alt="" className="absolute inset-0 size-full object-cover" />
  ) : (
    <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_120%,transparent_40%,rgba(0,0,0,0.55))]" />
  );

  const gradient = {
    background: `radial-gradient(120% 90% at 30% 20%, hsl(${hue} 18% 42%), hsl(${(hue + 40) % 360} 22% 14%) 70%), linear-gradient(160deg, hsl(${hue} 25% 30%), hsl(${(hue + 60) % 360} 30% 8%))`,
  };

  return (
    <div
      className={cn(
        // Container query unit `cqw` is what keeps the type scaling with the
        // card instead of the viewport — the panel must look the same in the
        // 180px list thumbnail and the 380px detail view.
        "@container relative flex flex-col overflow-hidden rounded-md border bg-black",
        className,
      )}
      style={{ aspectRatio: `${layout.image.width} / ${layout.image.height}` }}
    >
      {/* On a full overlay the photograph *is* the card and the panel lies over
          its bottom, so the hero is painted behind everything and the flex
          column above it only positions the panel. On a card the hero occupies
          its own box and is cropped to it — which is what the compositor does,
          and why this is not simply full-bleed in both cases: the crop differs. */}
      {full ? (
        <div className="absolute inset-0" style={heroSrc ? undefined : gradient}>
          {heroImage}
        </div>
      ) : null}

      <div
        className="relative min-h-0 flex-1"
        style={full || heroSrc ? undefined : gradient}
      >
        {full ? null : heroImage}

        {/* The headline chip, bottom-left of the hero share — whose bottom edge
            *is* the top of the panel, on either template. `cqw` throughout
            because the container query resolves against the width and the
            compositor's gap is a fraction of the height: at 896×1120 a share of
            height is 1.25× the same share of width. Drawn on `full_overlay`
            only, and only when the Page has a word for it. */}
        {full && page.badge_text ? (
          <span
            className="absolute font-bold uppercase leading-none"
            style={{
              left: scale(layout.image.edge_margin_ratio * layout.image.width),
              bottom: `${layout.badge.gap_ratio * 1.25 * 100}cqw`,
              backgroundColor: layout.badge.color,
              color: layout.badge.text_color,
              fontSize: `${(layout.badge.font_size_px / layout.image.width) * 100}cqw`,
              fontFamily: "Arial, Helvetica, sans-serif",
              paddingInline: scale(layout.badge.padding_x_px),
              paddingBlock: scale(layout.badge.padding_y_px),
              // Clamped to half the height, as the compositor does — past that
              // resvg draws a stadium and this drew a rounded box.
              borderRadius: scale(
                Math.min(
                  layout.badge.radius_px,
                  (layout.badge.font_size_px + layout.badge.padding_y_px * 2) / 2,
                ),
              ),
            }}
          >
            {page.badge_text}
          </span>
        ) : null}

        <Watermark layout={layout} page={page} full={full} />

        {/* On the seam by default: `bottom-0` is the hero's own edge, and the
            50% translate puts half the disc onto the panel. */}
        {insetYRatio == null ? disc : null}
      </div>

      {/* Panel. `min-height` is the floor from `panel.ratio`; the content pushes
          it taller, up to `panel.max_ratio` — the same cap the compositor
          applies, without which the panel grows past the top of the card. */}
      <div
        className="relative shrink-0 overflow-hidden"
        style={{
          minHeight: `${layout.panel.ratio * 100}%`,
          maxHeight: `${layout.panel.max_ratio * 100}%`,
        }}
      >
        {/* Its own layer, so `opacity` never reaches the words. `opacity` on the
            panel would apply to its children; the compositor puts `fill-opacity`
            on the panel *rect* and draws the text at full strength over it. */}
        <div
          className="absolute inset-0"
          style={{
            backgroundColor: layout.panel.color,
            opacity: layout.panel.opacity,
          }}
        />
        <p
          // Not `uppercase`: the compositor draws the hook verbatim, and
          // shouting it here made the preview disagree with the PNG beside it.
          className="relative font-bold"
          style={{
            color: layout.text.color,
            // The panel is drawn at `image.width` in the real card, so the type
            // scales with the container rather than sitting at a fixed px. No
            // `clamp()` around it any more: the bounds were 10px and 19px, which
            // silently pinned the type at both ends of the size slider's range.
            fontSize: `${(layout.text.font_size_px / layout.image.width) * 100}cqw`,
            lineHeight: layout.text.line_height_ratio,
            textAlign: layout.text.align as "left" | "center" | "right",
            paddingLeft: scale(layout.text.padding.left_px),
            paddingRight: scale(layout.text.padding.right_px),
            paddingTop: scale(layout.text.padding.top_px),
            paddingBottom: scale(layout.text.padding.bottom_px),
          }}
        >
          {segments.length === 0 ? (
            <span className="opacity-25">No overlay text</span>
          ) : (
            segments.map((segment, index) => (
              <span
                key={index}
                style={segment.highlight ? { color: layout.highlight.color } : undefined}
              >
                {segment.text}
              </span>
            ))
          )}
        </p>
      </div>

      {/* Placed by the operator: against the card, not the hero, because the
          disc can now be anywhere including entirely on the panel. */}
      {insetYRatio == null ? null : disc}
    </div>
  );
}

/**
 * The mark, top-right, exactly as `page.watermark()` decides it.
 *
 * Three outcomes rather than the two this used to draw. It previously took a
 * bare `watermark_image_path` and printed a red "no watermark asset" box when
 * it was null — which is the *normal* state for eight of the ten Pages, none of
 * which has artwork committed to the repo. They publish either an uploaded mark
 * or their name as text, and the preview called both of them broken.
 *
 * Opted out is not the same as having no mark: `watermark_enabled` false means
 * the photograph publishes clean, and the compositor draws nothing at all.
 */
function Watermark({
  layout,
  page,
  full,
}: {
  layout: ResolvedLayout;
  page: Page;
  full: boolean;
}) {
  if (!page.watermark_enabled) return null;

  const mark = watermarkUrl(page);
  const scale = (px: number) => `${(px / layout.image.width) * 100}%`;
  // The compositor's own second cap, applied to the box the mark fits inside.
  const box = Math.min(layout.watermark.max_px, layout.image.width * 0.22);
  // `top_ratio` is a fraction of the *hero*. On a card this element's
  // containing block is the hero box, so a percentage already means that. On a
  // full overlay the hero is the whole card, so the same number has to be
  // expressed against the width instead: height is 1.25 × width at 4:5.
  const top = full
    ? `${layout.watermark.top_ratio * 1.25 * 100}cqw`
    : `${layout.watermark.top_ratio * 100}%`;
  const right = `${layout.image.edge_margin_ratio * 100}%`;

  if (mark) {
    return (
      // Two possible origins — the public bucket, or the API's `/assets` mount
      // through the proxy — and neither is in `next.config.ts`'s image hosts,
      // so `next/image` cannot load it.
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={mark}
        alt=""
        className="absolute object-contain drop-shadow"
        style={{ top, right, maxWidth: scale(box), maxHeight: scale(box) }}
      />
    );
  }

  // What the compositor draws when a Page has no image mark: its own text, or
  // failing that its name, right-anchored at 2.2% of width. Not a fallback for
  // a mark that failed to load — that raises — so this is a Page that publishes
  // a wordmark rather than a logo.
  return (
    <span
      className="absolute font-bold text-white/95"
      style={{
        top,
        right,
        fontSize: `${(Math.max(16, layout.image.width * 0.022) / layout.image.width) * 100}cqw`,
        fontFamily: "Arial, Helvetica, sans-serif",
      }}
    >
      {page.watermark_text || page.name}
    </span>
  );
}

/**
 * The inset diameter the compositor would use, in card pixels.
 *
 * The same clamp as `PortraitLayout.clamp`, and it has to be here as well as
 * there: the slider moves this preview on every drag, long before a save exists
 * to clamp anything, and a preview that draws a size the PNG will not is worse
 * than no preview.
 */
export function clampInset(
  sizePx: number | null | undefined,
  layout: ResolvedLayout,
): number {
  const portrait = layout.portrait;
  return Math.round(
    Math.min(
      layout.image.width * portrait.max_width_ratio,
      Math.max(portrait.min_px, sizePx ?? portrait.size_px),
    ),
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
