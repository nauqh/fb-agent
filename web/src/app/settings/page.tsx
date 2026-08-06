"use client";

import { useState } from "react";
import { ChevronDown, FileText } from "lucide-react";

import { ScreenHeader } from "@/components/screen";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { listPages, listPromptFiles } from "@/lib/api/pages";
import { LAYOUT } from "@/lib/fixtures/pages";
import { useQuery } from "@/lib/use-query";
import { cn } from "@/lib/utils";

/**
 * One Page, and nothing to type into.
 *
 * Read-only throughout, which is the honest shape rather than a missing
 * feature. Identity comes from Metricool. Layout is `layout.yml`. The prompts
 * are files precisely so they are reviewed in git rather than typed into a box,
 * and a textarea here would quietly undo that. What is left is a window onto
 * what the run is actually configured with — and every piece of it is edited
 * somewhere a diff can be read.
 */
export default function SettingsScreen() {
  const { data: pages } = useQuery(() => listPages(), []);
  const { data: prompts } = useQuery(() => listPromptFiles(), []);
  const page = pages?.[0];

  if (!page) {
    return (
      <div className="w-full max-w-3xl space-y-4">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-40" />
      </div>
    );
  }

  return (
    <div className="w-full max-w-3xl pb-16 lg:min-h-0 lg:flex-1 lg:overflow-y-auto">
      <ScreenHeader title="Settings" />

      <section className="space-y-6">
        <div>
          <h2 className="text-base font-medium">{page.name}</h2>
          <p className="pt-1 font-mono text-xs text-muted-foreground">
            facebook {page.facebook_page_id}
            <span className="mx-2">·</span>
            metricool {page.metricool_blog_id}
          </p>
          <p className="pt-1 text-xs text-muted-foreground">
            Identity comes from Metricool and is not editable here.
          </p>
        </div>

        <Separator />

        <div className="grid gap-6 sm:grid-cols-2">
          <div className="space-y-2">
            <Label>Watermark</Label>
            {page.watermark_image_path ? (
              <>
                <div className="flex items-center gap-2">
                  <span className="rounded bg-black px-2 py-1.5">
                    {/* eslint-disable-next-line @next/next/no-img-element -- the
                        committed asset at its own 350×74, not a content image. */}
                    <img
                      src="/watermarks/history-retraced.png"
                      alt={`${page.name} watermark`}
                      className="h-4 w-auto"
                    />
                  </span>
                  <code className="text-xs">{page.watermark_image_path}</code>
                </div>
                <p className="text-xs leading-relaxed text-muted-foreground">
                  350×74 white-on-transparent, committed beside the font because the renderer
                  cannot work without it. A missing file is an error — the old compositor
                  silently printed the name as text instead, and nobody noticed for months.
                </p>
              </>
            ) : (
              <>
                <p className="text-sm text-destructive">missing</p>
                <p className="text-xs leading-relaxed text-muted-foreground">
                  Nothing to composite. This is a broken Page, not a styling choice.
                </p>
              </>
            )}
          </div>
        </div>

        <Separator />

        <div className="space-y-3">
          <div>
            <h3 className="text-sm font-medium">Prompts</h3>
            <p className="pt-1 text-xs leading-relaxed text-muted-foreground">
              Files in <code>api/prompts/</code>. Edited in your editor, reviewed in git — they
              were columns once, and every copy drifted against the code it was pasted from.
            </p>
          </div>

          <div className="divide-y rounded-lg border">
            {prompts?.map((prompt) => (
              <PromptRow key={prompt.filename} {...prompt} />
            ))}
          </div>
        </div>

        <Separator />

        <div className="space-y-3">
          <div>
            <h3 className="text-sm font-medium">Composed Image</h3>
            <p className="pt-1 text-xs text-muted-foreground">
              <code>api/config/layout.yml</code>. One form, one size, identical for every Page.
            </p>
          </div>
          <dl className="grid grid-cols-2 gap-x-6 gap-y-2 rounded-lg border p-4 text-xs sm:grid-cols-4">
            <Constant label="Size" value={`${LAYOUT.width} × ${LAYOUT.height}`} />
            <Constant label="Panel floor" value={`${LAYOUT.panelRatio * 100}%`} />
            <Constant label="Font" value={`Arial Bold ${LAYOUT.fontSizePx}px`} />
            <Constant label="Highlight" value={LAYOUT.highlightColor} swatch />
          </dl>
        </div>
      </section>
    </div>
  );
}

function PromptRow({
  filename,
  chars,
  body,
}: {
  filename: string;
  chars: number;
  body: string;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen((current) => !current)}
        className="flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-muted/50"
      >
        <FileText className="size-4 shrink-0 text-muted-foreground" />
        <span className="flex-1 font-mono text-xs">{filename}</span>
        <span className="tabular-nums text-xs text-muted-foreground">
          {chars.toLocaleString()} chars
        </span>
        <ChevronDown
          className={cn("size-4 text-muted-foreground transition-transform", open && "rotate-180")}
        />
      </button>
      {open ? (
        <pre className="max-h-96 overflow-auto whitespace-pre-wrap border-t bg-muted/40 px-4 py-3 font-mono text-[11px] leading-relaxed text-muted-foreground">
          {body}
        </pre>
      ) : null}
    </div>
  );
}

function Constant({
  label,
  value,
  swatch,
}: {
  label: string;
  value: string;
  swatch?: boolean;
}) {
  return (
    <div>
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="flex items-center gap-1.5 pt-0.5 font-mono">
        {swatch ? (
          <span
            className="size-2.5 rounded-full border"
            style={{ backgroundColor: value }}
          />
        ) : null}
        {value}
      </dd>
    </div>
  );
}
