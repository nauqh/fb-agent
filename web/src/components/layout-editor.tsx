"use client";

import { useState } from "react";
import { Loader2, RotateCcw } from "lucide-react";
import { toast } from "sonner";

import { splitOnHighlights } from "@/components/composed-image";
import { HookField } from "@/components/hook-field";
import { Loading } from "@/components/loading";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  getPageLayout,
  resetPageLayout,
  savePageLayout,
  type LayoutPatch,
  type ResolvedLayout,
} from "@/lib/api/layout";
import {
  removeWatermark,
  updatePage,
  uploadWatermark,
  watermarkUrl,
} from "@/lib/api/pages";
import { usePageScope } from "@/lib/page-scope";
import type { Page } from "@/lib/types";
import { emit } from "@/lib/store";
import { useQuery } from "@/lib/use-query";
import { cn } from "@/lib/utils";

/**
 * A hook at the length the writer actually produces — near the 65-word cap.
 *
 * The one-line sample this replaced flattered every setting: at 36px it wrapped
 * to two lines, the panel sat on its `ratio` floor, and nothing about padding,
 * line count or the `max_ratio` cap could be judged from it. The panel grows to
 * fit its text, so a short sample hides the behaviour the screen exists to show.
 */
const SAMPLE =
  "In 1925, a deadly diphtheria outbreak threatened to wipe out the isolated " +
  "town of Nome, Alaska. The only serum was a thousand miles away, every port " +
  "was frozen solid, and twenty mushers ran it through a −50°F blizzard in " +
  "five and a half days.";

/**
 * Edit one Page's Composed Image, with the card beside it.
 *
 * Same shape as the old app's panel — controls on the left, a sticky preview on
 * the right, both driven by the *unsaved* values so a slider moves the card
 * rather than the last save. Its sample text is editable for the same reason:
 * the thing being judged is how a real hook sits in the panel, and a fixed
 * string cannot show you the two-line case.
 *
 * The preview is drawn in the browser rather than fetched. That is how the
 * queue and the draft sheet already work (`ComposedImage`), and it is why
 * editing shows up as you type instead of after a round trip. It is an
 * approximation of resvg, not resvg — good enough to choose a colour or a size,
 * not proof of the pixels. The published image is still the compositor's.
 *
 * Image dimensions and the font are absent on purpose. 4:5 is the tallest ratio
 * Facebook renders in feed, and a font family that does not match the TTF's
 * name table makes resvg substitute a serif *silently* and still return a valid
 * PNG — neither is a thing to offer in a form.
 */
export function LayoutEditor() {
  const { page, pageId } = usePageScope();
  const { data, refresh } = useQuery(() => getPageLayout(pageId!), [pageId], {
    enabled: pageId !== null,
  });

  // Unsaved changes only. Merged over the resolved layout for the preview, so
  // an untouched field keeps tracking the file rather than being captured as a
  // copy of whatever it said when this screen opened.
  const [draft, setDraft] = useState<LayoutPatch>({});
  const [saving, setSaving] = useState(false);

  if (!data || !page) return <Loading label="Loading layout" className="h-96" />;

  const shown = preview(data.layout, draft);
  const dirty = Object.keys(draft).length > 0;

  function set<K extends keyof LayoutPatch>(key: K, value: LayoutPatch[K]) {
    setDraft((current) => ({ ...current, [key]: value }));
  }

  async function save() {
    if (pageId === null) return;
    setSaving(true);
    try {
      await savePageLayout(pageId, draft);
      setDraft({});
      toast.success(`${page!.name}'s layout saved`);
      await refresh();
      emit();
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "Could not save");
    } finally {
      setSaving(false);
    }
  }

  async function reset() {
    if (pageId === null) return;
    setSaving(true);
    try {
      await resetPageLayout(pageId);
      setDraft({});
      toast.success(`${page!.name} is back on the defaults`);
      await refresh();
      emit();
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "Could not reset");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_20rem]">
      <div className="space-y-5">
        {/* Three sections, named for the three things on the card: the mark
            stamped on the hero, the box it sits above, and the type inside that
            box. Grouped this way rather than by which model field they came
            from — "Marks" held the highlight colour and the logo, which are the
            same word and not the same object. The old app's split is the same
            one (`Text overlay typography` carries the font *and* its padding,
            because padding is a property of the text block). */}
        <Group title="Template">
          <div className="sm:col-span-2">
            <Choice
              label="Card form"
              value={shown.template}
              options={["card", "full_overlay"]}
              changed={data.overridden.includes("template")}
              onChange={(v) => set("template", v as "card" | "full_overlay")}
            />
            <p className="pt-1 text-[0.7rem] text-muted-foreground">
              {shown.template === "card"
                ? "Hero on top, panel below it, dividing the height between them."
                : "The photograph fills the card and the panel lies over its bottom."}
            </p>
          </div>

          {/* Opacity is a full-overlay control and only that. On a card there is
              nothing behind the panel, so the setting does nothing but let one
              brand's cards drift off the house style; here it is the whole
              difference between type on a photograph and a black band over it. */}
          {shown.template === "full_overlay" ? (
            <Range
              label="Panel opacity"
              hint="At 100% the panel covers the picture it is meant to sit on."
              value={shown.panel.opacity}
              min={0}
              max={1}
              step={0.05}
              format={(v) => `${Math.round(v * 100)}%`}
              changed={data.overridden.includes("panel_opacity")}
              onChange={(v) => set("panel_opacity", v)}
            />
          ) : null}
        </Group>

        {shown.template === "full_overlay" ? (
          <Group title="Headline badge">
            <Colour
              label="Colour"
              value={shown.badge.color}
              changed={data.overridden.includes("badge_color")}
              onChange={(v) => set("badge_color", v)}
            />
            <Range
              label="Size"
              value={shown.badge.font_size_px}
              min={12}
              max={48}
              step={1}
              format={(v) => `${v}px`}
              changed={data.overridden.includes("badge_font_size_px")}
              onChange={(v) => set("badge_font_size_px", v)}
            />
            <div className="sm:col-span-2">
              <Badge page={page} />
            </div>
          </Group>
        ) : null}

        <Group title="Watermark">
          <Range
            label="Size"
            hint="Capped again at 22% of width by the compositor."
            value={shown.watermark.max_px}
            min={60}
            max={260}
            step={2}
            format={(v) => `${v}px`}
            changed={data.overridden.includes("watermark_max_px")}
            onChange={(v) => set("watermark_max_px", v)}
          />
          {/* Its own two cells, spanning the row: the image and the text that
              replaces it belong beside each other, not stacked under a slider. */}
          <div className="sm:col-span-2">
            <Watermark page={page} />
          </div>
        </Group>

        <Group title="Text panel">
          {/* Background only. Height and opacity track `layout.yml` for every
              Page, on the same grounds as line height below: the panel already
              grows to fit its text, so its floor is a typographic decision made
              once, and an opacity that differs per Page is a way for one brand's
              cards to drift off the house style without anyone choosing it. The
              API still takes `panel_ratio` and `panel_opacity` — this is a
              screen that does not offer them, not values that stopped existing. */}
          <Colour
            label="Background"
            value={shown.panel.color}
            changed={data.overridden.includes("panel_color")}
            onChange={(v) => set("panel_color", v)}
          />
        </Group>

        <Group title="Text overlay">
          <Range
            label="Size"
            hint="Fixed — there is no autofit. The panel grows, the type does not shrink."
            value={shown.text.font_size_px}
            min={20}
            max={72}
            step={1}
            format={(v) => `${v}px`}
            changed={data.overridden.includes("text_font_size_px")}
            onChange={(v) => set("text_font_size_px", v)}
          />
          {/* No line-height control. It tracks `layout.yml` for every Page: the
              panel already grows to fit, so the leading is a typographic
              decision made once rather than a knob per Page. The API still
              takes `text_line_height_ratio` — this is a screen that does not
              offer it, not a value that stopped existing. */}
          <Choice
            label="Align"
            value={shown.text.align}
            options={["left", "center", "right"]}
            changed={data.overridden.includes("text_align")}
            onChange={(v) => set("text_align", v)}
          />
          {/* Case is a drawing setting, so the hook stays in the case the
              writer produced and every existing draft follows this switch with
              no regeneration. It applies to the highlight phrases too — both
              sides, or an exact-substring match finds nothing and the gold
              disappears. */}
          <Choice
            label="Case"
            value={shown.text.uppercase ? "capitals" : "as_written"}
            options={["as_written", "capitals"]}
            changed={data.overridden.includes("text_uppercase")}
            onChange={(v) => set("text_uppercase", v === "capitals")}
          />
          <Colour
            label="Colour"
            value={shown.text.color}
            changed={data.overridden.includes("text_color")}
            onChange={(v) => set("text_color", v)}
          />
          <Colour
            label="Highlight"
            hint="Phrases the writer marks verbatim."
            value={shown.highlight.color}
            changed={data.overridden.includes("highlight_color")}
            onChange={(v) => set("highlight_color", v)}
          />
          {/* The four paddings are cells of the same grid as the rest, not a
              grid of their own inside one cell — nested, they were half the
              width of every other control and read as a different kind of
              thing. */}
          {(
            [
              ["Pad left", "text_padding_left_px", shown.text.padding.left_px],
              ["Pad right", "text_padding_right_px", shown.text.padding.right_px],
              ["Pad top", "text_padding_top_px", shown.text.padding.top_px],
              ["Pad bottom", "text_padding_bottom_px", shown.text.padding.bottom_px],
            ] as const
          ).map(([label, key, value]) => (
            <Range
              key={key}
              label={label}
              value={value}
              min={0}
              max={80}
              step={1}
              format={(v) => `${v}px`}
              changed={data.overridden.includes(key)}
              onChange={(v) => set(key, v)}
            />
          ))}
        </Group>

        <div className="flex flex-wrap items-center gap-2 border-t pt-4">
          <Button size="sm" onClick={save} disabled={!dirty || saving}>
            {saving ? <Loader2 className="size-3.5 animate-spin" /> : null}
            Save
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={reset}
            disabled={saving || (data.overridden.length === 0 && !dirty)}
          >
            <RotateCcw className="size-3.5" />
            Reset to defaults
          </Button>
          <p className="text-xs text-muted-foreground">
            {data.overridden.length === 0
              ? "On the defaults from config/layout.yml."
              : `${data.overridden.length} value${data.overridden.length === 1 ? "" : "s"} overridden for ${page.name}.`}
            {dirty ? " Unsaved changes shown in the preview." : ""}
          </p>
        </div>
      </div>

      <Preview layout={shown} page={page} />
    </div>
  );
}

/** The resolved layout with the unsaved edits laid over it, for the preview. */
function preview(base: ResolvedLayout, draft: LayoutPatch): ResolvedLayout {
  const at = <T,>(value: T | null | undefined, fallback: T): T =>
    value === undefined || value === null ? fallback : value;

  return {
    ...base,
    template: at(draft.template, base.template),
    badge: {
      ...base.badge,
      color: at(draft.badge_color, base.badge.color),
      font_size_px: at(draft.badge_font_size_px, base.badge.font_size_px),
    },
    panel: {
      ...base.panel,
      ratio: at(draft.panel_ratio, base.panel.ratio),
      color: at(draft.panel_color, base.panel.color),
      opacity: at(draft.panel_opacity, base.panel.opacity),
    },
    text: {
      ...base.text,
      font_size_px: at(draft.text_font_size_px, base.text.font_size_px),
      line_height_ratio: at(draft.text_line_height_ratio, base.text.line_height_ratio),
      align: at(draft.text_align, base.text.align),
      color: at(draft.text_color, base.text.color),
      uppercase: at(draft.text_uppercase, base.text.uppercase),
      padding: {
        left_px: at(draft.text_padding_left_px, base.text.padding.left_px),
        right_px: at(draft.text_padding_right_px, base.text.padding.right_px),
        top_px: at(draft.text_padding_top_px, base.text.padding.top_px),
        bottom_px: at(draft.text_padding_bottom_px, base.text.padding.bottom_px),
      },
    },
    highlight: { color: at(draft.highlight_color, base.highlight.color) },
    watermark: {
      ...base.watermark,
      max_px: at(draft.watermark_max_px, base.watermark.max_px),
    },
  };
}

/** Short phrases, as `overlay.txt` asks the writer for — not one long clause. */
const SAMPLE_HIGHLIGHTS = [
  "deadly diphtheria outbreak",
  "a thousand miles away",
  "five and a half days",
];

/**
 * The card, at 4:5, with the sample hook and its highlights below it.
 *
 * Percentages of the real 896px width throughout, so the preview is the same
 * shape at any rendered size. Sticky, because the controls are taller than it
 * is and a preview you have to scroll back to is not a preview.
 *
 * Four things here were drawn differently from the compositor, which is what
 * made the preview disagree with the published card:
 *
 * - **Opacity dimmed the text.** `opacity` on the panel applies to its
 *   children; the compositor puts `fill-opacity` on the panel *rect* and draws
 *   the text at full strength over it. At 50% the preview faded the words and
 *   the real card did not. Hence the separate background layer.
 * - **The text was vertically centred.** The compositor's first baseline is
 *   `padding.top + font_size` and the panel grows downward from there.
 * - **The mark was the page name in 8px text.** It is an image, at
 *   `watermark.max_px` capped at 22% of width, inset by `edge_margin_ratio`,
 *   `top_ratio` down the *hero* rather than the card.
 * - **The font was the app's sans.** The card is drawn in Arial Bold, which is
 *   wider — a hook that fit here could wrap to another line there.
 */
function Preview({ layout, page }: { layout: ResolvedLayout; page: Page }) {
  const [sample, setSample] = useState(SAMPLE);
  const [phrases, setPhrases] = useState<string[]>(SAMPLE_HIGHLIGHTS);
  const scale = (px: number) => `${(px / layout.image.width) * 100}%`;
  const mark = watermarkUrl(page);
  const full = layout.template === "full_overlay";
  // The compositor's own second cap, applied to the box the logo fits inside.
  const markBox = Math.min(layout.watermark.max_px, layout.image.width * 0.22);
  // `top_ratio` is a fraction of the hero, and on a full overlay the hero is
  // the whole card — so the mark hangs from the card's top rather than from the
  // bottom of the space above the panel. Same number, different denominator.
  const markTop = full
    ? `${layout.watermark.top_ratio * 1.25 * 100}cqw`
    : `${layout.watermark.top_ratio * 100}%`;
  // The third renderer of the same panel, after the compositor and
  // `ComposedImage`. It takes the case the same way both of those do — text and
  // phrases together, in the strings — or the switch beside it reads as a
  // control that does nothing, which is what this preview exists to prevent.
  const shout = (value: string) =>
    layout.text.uppercase ? value.toUpperCase() : value;
  const runs = splitOnHighlights(shout(sample), phrases.map(shout));

  return (
    <div className="space-y-2 lg:sticky lg:top-0 lg:self-start">
      {/* `container-type: inline-size` belongs here, on the card, not on the
          text. Putting it on the <p> gave `cqw` no valid container to resolve
          against — it fell back to the viewport and rendered the hook at about
          five times its real size, overflowing the card entirely. */}
      <div
        className="relative w-full overflow-hidden rounded-2xl border bg-muted [container-type:inline-size]"
        style={{ aspectRatio: `${layout.image.width} / ${layout.image.height}` }}
      >
        {/* Stands in for the hero, and fills the *whole* card rather than only
            the space above the panel. A real one would need a draft, and this is
            about the panel over it rather than the picture under it.

            Full-bleed because the two were flex siblings and their heights are
            fractional at most widths: the panel's `%` height rounds one way, the
            hero's `flex-1` the other, and the card's own light background showed
            through the half-pixel between them as a thin white line above the
            panel. Painting the hero behind everything leaves nothing to show
            through — the panel simply covers the bottom of it, which is what the
            compositor does anyway. */}
        <div className="absolute inset-0 bg-gradient-to-br from-slate-600 to-slate-800" />

        <div className="absolute inset-0 flex flex-col">
          {/* The hero's share of the height. Transparent — the gradient is
              behind it — and here only to hang the watermark off, whose
              `top_ratio` is a fraction of the hero rather than of the card. */}
          <div className="relative min-h-0 flex-1">
            {/* The chip, bottom-left of the hero share — whose bottom edge *is*
                the top of the panel, on either template. `cqw` throughout
                because the container query resolves against the width, and the
                compositor's gap is a fraction of the height: at 896×1120 a
                share of height is 1.25× the same share of width. */}
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
                  // Clamped to half the height, as the compositor does — past
                  // that resvg draws a stadium and this drew a rounded box.
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

            {!page.watermark_enabled ? null : mark ? (
              // The mark comes from one of two origins — the public bucket, or
              // the API's /assets mount through the proxy — and neither is in
              // next.config.ts's image hosts, so `next/image` cannot load it.
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={mark}
                alt=""
                className="absolute object-contain"
                style={{
                  right: scale(layout.image.edge_margin_ratio * layout.image.width),
                  top: markTop,
                  maxWidth: scale(markBox),
                  maxHeight: scale(markBox),
                }}
              />
            ) : (
              // What the compositor draws when a Page has no mark at all: its
              // name, right-anchored, at 2.2% of width. Not a fallback for a
              // logo that failed to load — that raises — so seeing this here
              // means this Page publishes without a wordmark.
              <span
                className="absolute font-bold text-white/95"
                style={{
                  right: scale(layout.image.edge_margin_ratio * layout.image.width),
                  top: markTop,
                  fontSize: `${Math.max(16, layout.image.width * 0.022) / layout.image.width * 100}cqw`,
                  fontFamily: "Arial, Helvetica, sans-serif",
                }}
              >
                {page.watermark_text || page.name}
              </span>
            )}
          </div>

          {/* `maxHeight` is `panel.max_ratio`, the same cap the compositor
              applies. Without it the panel grew past the top of the card as the
              sample text got longer, which is not what the real one does. */}
          <div
            className="relative shrink-0 overflow-hidden"
            style={{
              minHeight: `${layout.panel.ratio * 100}%`,
              maxHeight: `${layout.panel.max_ratio * 100}%`,
            }}
          >
            {/* Its own layer, so `opacity` never reaches the words. */}
            <div
              className="absolute inset-0"
              style={{
                backgroundColor: layout.panel.color,
                opacity: layout.panel.opacity,
              }}
            />
            <p
              className="relative"
              style={{
                color: layout.text.color,
                // The panel is drawn at `image.width` in the real card, so type
                // scales with the container rather than sitting at a fixed px.
                // As a share of the real 896px width, so the card is the same
                // shape at any rendered size.
                fontSize: `${(layout.text.font_size_px / layout.image.width) * 100}cqw`,
                lineHeight: layout.text.line_height_ratio,
                textAlign: layout.text.align as "left" | "center" | "right",
                fontFamily: "Arial, Helvetica, sans-serif",
                fontWeight: 700,
                paddingLeft: scale(layout.text.padding.left_px),
                paddingRight: scale(layout.text.padding.right_px),
                paddingTop: scale(layout.text.padding.top_px),
                paddingBottom: scale(layout.text.padding.bottom_px),
              }}
            >
              {runs.map((run, index) => (
                <span
                  key={index}
                  style={run.highlight ? { color: layout.highlight.color } : undefined}
                >
                  {run.text}
                </span>
              ))}
            </p>
          </div>
        </div>
      </div>

      {/* Under the card: the card is the thing being judged and stays at the
          top of the sticky column, where a change to any slider is visible
          without scrolling. The sample text is the input to it.

          `HookField` rather than a text box and a list of phrases, because it
          is what the review drawer already uses and the reason it exists there
          holds here: a typed phrase has to match the text exactly or it colours
          nothing, and retyping words that are already on screen is the one way
          to get that wrong. Select the words, press Highlight. */}
      <HookField
        value={sample}
        phrases={phrases}
        rows={6}
        onChange={setSample}
        onPhrasesChange={setPhrases}
      />
    </div>
  );
}

/**
 * The Page's watermark: what it is drawing with, and how to change it.
 *
 * Two sources, and the screen says which is in force. A committed asset under
 * `api/assets/` cannot 404 and needs no upload, which is why the two Pages that
 * have one keep it. The other eight have no artwork in the repo and no way to
 * put it there, so they publish unmarked — this is their route.
 */
function Watermark({ page }: { page: Page }) {
  const [busy, setBusy] = useState(false);
  const [text, setText] = useState(page.watermark_text ?? "");
  const url = watermarkUrl(page);
  const hasImage = Boolean(page.watermark_upload_path || page.watermark_image_path);

  async function setEnabled(next: boolean) {
    try {
      await updatePage(page.id, { watermark_enabled: next });
      toast.success(next ? "Cards will carry a mark" : "Cards publish unmarked");
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "Could not save");
    }
  }

  async function saveText() {
    const wanted = text.trim();
    if (wanted === (page.watermark_text ?? "")) return;
    try {
      // Empty is a clear, not a blank: null means "print the Page's name",
      // which is what a Page with no text and no logo has always drawn.
      await updatePage(page.id, { watermark_text: wanted || null });
      toast.success(wanted ? `Fallback text is “${wanted}”` : "Back to the Page's name");
    } catch (cause) {
      setText(page.watermark_text ?? "");
      toast.error(cause instanceof Error ? cause.message : "Could not save");
    }
  }

  async function choose(file: File | undefined) {
    if (!file) return;
    setBusy(true);
    try {
      await uploadWatermark(page.id, file);
      toast.success(`${page.name}'s watermark uploaded`);
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "Could not upload");
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    setBusy(true);
    try {
      await removeWatermark(page.id);
      toast.success("Upload removed");
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "Could not remove");
    } finally {
      setBusy(false);
    }
  }

  return (
    // Two cells of the section's own grid, so the image and the text that
    // stands in for it sit side by side and line up with every other control.
    // Stacked, the text field read as a caption on the thumbnail above it.
    <div className="grid gap-x-4 gap-y-3 sm:grid-cols-2">
      <div className="sm:col-span-2">
        {/* A tick, not a pair of buttons: this is one binary thing that is on
            by default, and a two-button group implies two choices of equal
            weight. */}
        <label className="flex cursor-pointer items-center gap-2 text-xs">
          <input
            type="checkbox"
            checked={page.watermark_enabled}
            onChange={(event) => void setEnabled(event.target.checked)}
            className="size-3.5 cursor-pointer accent-primary"
          />
          Stamp a mark on this Page&apos;s cards
        </label>
        <p className="pt-1 text-[0.7rem] text-muted-foreground">
          {page.watermark_enabled
            ? "The image below, or the fallback text where there is no image."
            : "Off — the photograph publishes clean. Neither image nor text is drawn."}
        </p>
      </div>

      <div className={cn("space-y-1", !page.watermark_enabled && "opacity-50")}>
        {/* `block`, because `Input` is a bare <input> and so inline-block: an
            inline label leaves it on the same line, and `space-y` only adds a
            margin it has no reason to break at. */}
        <label className="block text-xs">Watermark image</label>
        <div className="flex items-center gap-3">
          {/* Square, and big enough to read — the compositor fits the mark into
              a square box too (`max_px`, capped at 22% of width), so this is
              the shape it is actually judged in. At 56px it was a smudge that
              could not be told apart from the wrong file.

              Dark, not the transparency checker the old app used here. Ours is
              white ink for a photograph: on a light checker it is invisible,
              which is the one thing a thumbnail must not be. */}
          <div className="flex size-24 shrink-0 items-center justify-center rounded border bg-slate-700 p-2">
            {url ? (
              // Same two origins as the preview's mark — see there.
              // eslint-disable-next-line @next/next/no-img-element
              <img src={url} alt="" className="max-h-full max-w-full object-contain" />
            ) : (
              <span className="text-[0.6rem] text-white/70">None</span>
            )}
          </div>
          <div className="space-y-1.5">
            <div className="flex flex-wrap items-center gap-2">
              <Button size="sm" variant="outline" disabled={busy} asChild>
                <label className="cursor-pointer">
                  {busy ? <Loader2 className="size-3.5 animate-spin" /> : null}
                  {page.watermark_upload_path ? "Replace" : "Upload"}
                  <input
                    type="file"
                    accept="image/png,image/jpeg"
                    className="hidden"
                    onChange={(event) => {
                      void choose(event.target.files?.[0]);
                      // Cleared, so choosing the same file twice fires again.
                      event.target.value = "";
                    }}
                  />
                </label>
              </Button>
              {page.watermark_upload_path ? (
                <Button size="sm" variant="ghost" disabled={busy} onClick={remove}>
                  Remove
                </Button>
              ) : null}
            </div>
            <p className="text-[0.7rem] text-muted-foreground">
              {page.watermark_upload_path
                ? "An uploaded mark. It wins over any committed asset."
                : page.watermark_image_path
                  ? "A committed asset in the repo. An upload would override it."
                  : "No image mark — the fallback text is what gets stamped."}
            </p>
          </div>
        </div>
      </div>

      <div className={cn("space-y-1", !page.watermark_enabled && "opacity-50")}>
        <label className="block text-xs" htmlFor="watermark-text">
          Fallback text
        </label>
        <Input
          id="watermark-text"
          value={text}
          placeholder={page.name}
          onChange={(event) => setText(event.target.value)}
          // Saved on blur rather than per keystroke: this is a Page row, not
          // the unsaved layout patch, and a PATCH per character would write ten
          // rows to spell a word. Empty clears it back to the Page's name.
          onBlur={() => void saveText()}
          className="h-8 text-xs"
        />
        <p className="text-[0.7rem] text-muted-foreground">
          {hasImage
            ? "Only drawn if the image beside it is removed."
            : `Drawn top-right, right now. Blank means this Page's name — “${page.name}”.`}
        </p>
      </div>
    </div>
  );
}

/**
 * The word in the headline chip, stored on the Page.
 *
 * Per Page rather than per draft for now: one word saying what the Page
 * publishes is most of the value, and a label chosen per post needs the writer
 * to return one and the review drawer to edit it. Blank draws no chip at all,
 * which is what a Page on this template that does not want one wants.
 */
function Badge({ page }: { page: Page }) {
  const [text, setText] = useState(page.badge_text ?? "");

  async function save() {
    const wanted = text.trim();
    if (wanted === (page.badge_text ?? "")) return;
    try {
      await updatePage(page.id, { badge_text: wanted || null });
      toast.success(wanted ? `Badge reads “${wanted.toUpperCase()}”` : "Badge removed");
    } catch (cause) {
      setText(page.badge_text ?? "");
      toast.error(cause instanceof Error ? cause.message : "Could not save");
    }
  }

  return (
    <div className="space-y-1">
      <label className="block text-xs" htmlFor="badge-text">
        Label
      </label>
      <Input
        id="badge-text"
        value={text}
        placeholder="NEWS"
        onChange={(event) => setText(event.target.value)}
        // On blur, like the fallback text: this is a Page row, and a PATCH per
        // keystroke would write four of them to spell one word.
        onBlur={() => void save()}
        className="h-8 text-xs uppercase"
      />
      <p className="text-[0.7rem] text-muted-foreground">
        {page.badge_text
          ? "Drawn bottom-left, just above the panel. Always upper-cased."
          : "Blank draws no chip."}
      </p>
    </div>
  );
}

/**
 * A titled block of controls, two to a row.
 *
 * Columns rather than one field per row, which is how the old app's settings
 * panel reads (`facebook-prompts-settings-panel.tsx`, `grid gap-4
 * sm:grid-cols-2`). Stacked, sixteen controls made a column tall enough that
 * the sticky preview had scrolled out of the useful range by the padding
 * fields — and padding is the one group you cannot judge without watching the
 * card. A field that needs the width wraps itself in `sm:col-span-2`.
 */
function Group({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-3">
      {/* Full-strength, like every other heading on this screen. Small caps
          already separate it from the controls under it; greying it as well
          made the group read as switched off. */}
      <h3 className="text-xs font-semibold uppercase tracking-wide">{title}</h3>
      <div className="grid gap-x-4 gap-y-3 sm:grid-cols-2">{children}</div>
    </section>
  );
}

/** A labelled control. `changed` marks a value this Page overrides. */
function Field({
  label,
  hint,
  changed,
  value,
  children,
}: {
  label: string;
  hint?: string;
  changed?: boolean;
  value: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1">
      <div className="flex items-baseline justify-between gap-2">
        <label className="flex items-center gap-1.5 text-xs">
          {label}
          {changed ? (
            <span
              title="Overridden for this Page"
              className="size-1.5 rounded-full bg-primary"
            />
          ) : null}
        </label>
        <span className="text-xs tabular-nums text-muted-foreground">{value}</span>
      </div>
      {children}
      {hint ? <p className="text-[0.7rem] text-muted-foreground">{hint}</p> : null}
    </div>
  );
}

function Range({
  label,
  hint,
  value,
  min,
  max,
  step,
  format,
  changed,
  onChange,
}: {
  label: string;
  hint?: string;
  value: number;
  min: number;
  max: number;
  step: number;
  format: (value: number) => string;
  changed?: boolean;
  onChange: (value: number) => void;
}) {
  // The filled portion, as a percentage. WebKit's track cannot see the thumb,
  // so the fill is a gradient stop and this is the only way to place it.
  const fill = max <= min ? 0 : Math.min(100, Math.max(0, ((value - min) / (max - min)) * 100));

  return (
    <Field label={label} hint={hint} changed={changed} value={format(value)}>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
        className="range-input w-full"
        style={{ "--range-fill": `${fill}%` } as React.CSSProperties}
      />
    </Field>
  );
}

function Colour({
  label,
  hint,
  value,
  changed,
  onChange,
}: {
  label: string;
  hint?: string;
  value: string;
  changed?: boolean;
  onChange: (value: string) => void;
}) {
  return (
    <Field label={label} hint={hint} changed={changed} value={value}>
      <div className="flex items-center gap-2">
        <input
          type="color"
          value={value}
          onChange={(event) => onChange(event.target.value)}
          aria-label={label}
          className="size-7 cursor-pointer rounded border bg-transparent"
        />
        <Input
          value={value}
          onChange={(event) => onChange(event.target.value)}
          className="h-7 w-28 font-mono text-xs"
        />
      </div>
    </Field>
  );
}

function Choice({
  label,
  value,
  options,
  changed,
  onChange,
}: {
  label: string;
  value: string;
  options: string[];
  changed?: boolean;
  onChange: (value: string) => void;
}) {
  return (
    <Field label={label} changed={changed} value={value}>
      <div className="flex gap-1">
        {options.map((option) => (
          <button
            key={option}
            type="button"
            onClick={() => onChange(option)}
            className={cn(
              "flex-1 rounded-md border px-2 py-1 text-xs capitalize transition-colors",
              option === value
                ? "border-primary bg-primary/10 text-primary"
                : "text-muted-foreground hover:bg-muted",
            )}
          >
            {/* The value is what the API takes; the underscore in
                `full_overlay` is not for reading. */}
            {option.replace(/_/g, " ")}
          </button>
        ))}
      </div>
    </Field>
  );
}
