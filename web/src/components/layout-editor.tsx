"use client";

import { useState } from "react";
import { Loader2, RotateCcw } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  getPageLayout,
  resetPageLayout,
  savePageLayout,
  type LayoutPatch,
  type ResolvedLayout,
} from "@/lib/api/layout";
import { usePageScope } from "@/lib/page-scope";
import { emit } from "@/lib/store";
import { useQuery } from "@/lib/use-query";
import { cn } from "@/lib/utils";

const SAMPLE =
  "In 1925, a deadly outbreak threatened to wipe out isolated Nome, Alaska.";

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

  if (!data || !page) return <Skeleton className="h-96 rounded-xl" />;

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
        <Group title="Panel">
          <Range
            label="Height"
            hint="Floor, not a cap — the panel grows to fit the text."
            value={shown.panel.ratio}
            min={0.1}
            max={0.6}
            step={0.01}
            format={(v) => `${Math.round(v * 100)}%`}
            changed={data.overridden.includes("panel_ratio")}
            onChange={(v) => set("panel_ratio", v)}
          />
          <Colour
            label="Background"
            value={shown.panel.color}
            changed={data.overridden.includes("panel_color")}
            onChange={(v) => set("panel_color", v)}
          />
          <Range
            label="Opacity"
            value={shown.panel.opacity}
            min={0}
            max={1}
            step={0.05}
            format={(v) => `${Math.round(v * 100)}%`}
            changed={data.overridden.includes("panel_opacity")}
            onChange={(v) => set("panel_opacity", v)}
          />
        </Group>

        <Group title="Text">
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
          <Range
            label="Line height"
            value={shown.text.line_height_ratio}
            min={1}
            max={2}
            step={0.02}
            format={(v) => v.toFixed(2)}
            changed={data.overridden.includes("text_line_height_ratio")}
            onChange={(v) => set("text_line_height_ratio", v)}
          />
          <Choice
            label="Align"
            value={shown.text.align}
            options={["left", "center", "right"]}
            changed={data.overridden.includes("text_align")}
            onChange={(v) => set("text_align", v)}
          />
          <Colour
            label="Colour"
            value={shown.text.color}
            changed={data.overridden.includes("text_color")}
            onChange={(v) => set("text_color", v)}
          />
          <div className="grid grid-cols-2 gap-x-4">
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
          </div>
        </Group>

        <Group title="Marks">
          <Colour
            label="Highlight"
            hint="Phrases the writer marks verbatim."
            value={shown.highlight.color}
            changed={data.overridden.includes("highlight_color")}
            onChange={(v) => set("highlight_color", v)}
          />
          <Range
            label="Watermark size"
            hint="Capped again at 22% of width by the compositor."
            value={shown.watermark.max_px}
            min={60}
            max={260}
            step={2}
            format={(v) => `${v}px`}
            changed={data.overridden.includes("watermark_max_px")}
            onChange={(v) => set("watermark_max_px", v)}
          />
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

      <Preview layout={shown} pageName={page.name} />
    </div>
  );
}

/** The resolved layout with the unsaved edits laid over it, for the preview. */
function preview(base: ResolvedLayout, draft: LayoutPatch): ResolvedLayout {
  const at = <T,>(value: T | null | undefined, fallback: T): T =>
    value === undefined || value === null ? fallback : value;

  return {
    ...base,
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

/**
 * The card, at 4:5, with an editable sample hook.
 *
 * Percentages of the real 896px width throughout, so the preview is the same
 * shape at any rendered size. Sticky, because the controls are taller than it
 * is and a preview you have to scroll back to is not a preview.
 */
function Preview({ layout, pageName }: { layout: ResolvedLayout; pageName: string }) {
  const [sample, setSample] = useState(SAMPLE);
  const scale = (px: number) => `${(px / layout.image.width) * 100}%`;

  return (
    <div className="space-y-2 lg:sticky lg:top-0 lg:self-start">
      <div
        className="relative w-full overflow-hidden rounded-lg border bg-muted"
        style={{ aspectRatio: `${layout.image.width} / ${layout.image.height}` }}
      >
        {/* Stands in for the hero. A real one would need a draft, and this is
            about the panel over it rather than the picture under it. */}
        <div className="absolute inset-0 bg-gradient-to-br from-slate-600 to-slate-800" />

        <div
          className="absolute right-0 top-0 flex items-center justify-end"
          style={{
            width: scale(layout.watermark.max_px),
            margin: scale(layout.image.edge_margin_ratio * layout.image.width),
          }}
        >
          <span className="truncate text-[0.5rem] font-semibold text-white/90">
            {pageName}
          </span>
        </div>

        <div
          className="absolute inset-x-0 bottom-0 flex flex-col justify-center"
          style={{
            minHeight: `${layout.panel.ratio * 100}%`,
            backgroundColor: layout.panel.color,
            opacity: layout.panel.opacity,
            paddingLeft: scale(layout.text.padding.left_px),
            paddingRight: scale(layout.text.padding.right_px),
            paddingTop: scale(layout.text.padding.top_px),
            paddingBottom: scale(layout.text.padding.bottom_px),
          }}
        >
          <p
            style={{
              color: layout.text.color,
              // The panel is drawn at `image.width` in the real card, so type
              // scales with the container rather than sitting at a fixed px.
              fontSize: `calc(${(layout.text.font_size_px / layout.image.width) * 100} * 1cqw)`,
              lineHeight: layout.text.line_height_ratio,
              textAlign: layout.text.align as "left" | "center" | "right",
            }}
            className="[container-type:inline-size] font-bold"
          >
            {sample}
          </p>
        </div>
      </div>

      <Input
        value={sample}
        onChange={(event) => setSample(event.target.value)}
        aria-label="Sample text"
        className="h-7 text-xs"
      />
      <p className="text-[0.7rem] text-muted-foreground">
        Approximate. The published image is drawn by the compositor, not here.
      </p>
    </div>
  );
}

function Group({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-3">
      <h3 className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {title}
      </h3>
      {children}
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
  return (
    <Field label={label} hint={hint} changed={changed} value={format(value)}>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
        className="h-1 w-full cursor-pointer appearance-none rounded bg-muted accent-primary"
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
            {option}
          </button>
        ))}
      </div>
    </Field>
  );
}
