"use client";

import { useState } from "react";
import { Loader2, Rocket, Trash2, UploadCloud } from "lucide-react";
import { toast } from "sonner";

import { ScreenHeader } from "@/components/screen";
import { QueryError } from "@/components/query-error";
import { Button } from "@/components/ui/button";
import { Loading } from "@/components/loading";
import { deleteCtaTemplate, getYoutubeConfig, listCtaTemplates, uploadCtaTemplate } from "@/lib/api/youtube";
import { emit } from "@/lib/store";
import { useQuery } from "@/lib/use-query";

/**
 * The Shorts tool's window onto its own configuration. Read-only, matching the
 * incumbent Settings screen's tone — the numbers that matter here are "is it
 * configured at all", which is presence, not values.
 */
export default function ShortsSettingsScreen() {
  const { data: config, error: configError, refresh: refreshConfig } = useQuery(getYoutubeConfig, []);
  const { data: templates, error: templatesError, loading, refresh: refreshTemplates } =
    useQuery(listCtaTemplates, []);

  async function removeClip(id: number) {
    try {
      await deleteCtaTemplate(id);
      emit();
      void refreshTemplates();
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "Could not remove clip");
    }
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <ScreenHeader
        title="Shorts Settings"
        hint="How the tool is wired. Editing arrives later."
      />

      <div className="flex flex-col gap-6">
        <section className="flex flex-col gap-3">
          <h2 className="text-sm font-medium">Configuration</h2>
          {configError ? (
            <QueryError error={configError} onRetry={refreshConfig} />
          ) : config ? (
            <div className="max-w-xl rounded-2xl border bg-card p-5">
              <dl className="flex flex-col gap-3 text-sm">
                <ConfigRow label="YouTube API key" ok={config.youtube_api_key_configured} note="powers the channel Shorts list" />
                <ConfigRow label="Cookies" ok={config.cookies_configured} note="the browser export that survives bot-checks" />
                <ConfigRow label="Download proxy" ok={config.proxy_configured} note="residential egress, when a datacenter IP is blocked" />
                <ConfigRow label="ffmpeg" ok={config.ffmpeg_configured} note="the trim + CTA concat engine" />
                <div className="flex items-center justify-between gap-4 border-t pt-3">
                  <span className="text-muted-foreground">File bucket</span>
                  <span className="font-mono text-xs">{config.bucket}</span>
                </div>
              </dl>
            </div>
          ) : null}
        </section>

        <section className="flex flex-col gap-3">
          <h2 className="text-sm font-medium">CTA clips</h2>
          {templatesError ? (
            <QueryError error={templatesError} onRetry={refreshTemplates} />
          ) : loading || !templates ? (
            <Loading label="Loading clips" className="h-32" />
          ) : templates.length === 0 ? (
            <p className="max-w-xl rounded-2xl border border-dashed p-8 text-center text-sm text-muted-foreground">
              No clips yet. Add one on Produce — it&rsquo;s the clip appended to every video.
            </p>
          ) : (
            <div className="max-w-xl rounded-2xl border bg-card">
              <ul className="divide-y">
                {templates.map((template) => (
                  <li key={template.id} className="flex items-center justify-between gap-3 px-4 py-3">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium">{template.title}</p>
                      <p className="truncate font-mono text-[11px] text-muted-foreground">
                        {template.cta_video_url}
                      </p>
                    </div>
                    <Button
                      variant="ghost"
                      size="icon"
                      aria-label={`Remove ${template.title}`}
                      onClick={() => void removeClip(template.id)}
                    >
                      <Trash2 className="size-4" />
                    </Button>
                  </li>
                ))}
              </ul>
              <div className="border-t p-3">
                <ClipUpload onUploaded={() => void refreshTemplates()} />
              </div>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

function ConfigRow({ label, ok, note }: { label: string; ok: boolean; note: string }) {
  return (
    <div className="flex items-center justify-between gap-4">
      <div className="min-w-0">
        <p className="font-medium">{label}</p>
        <p className="truncate text-xs text-muted-foreground">{note}</p>
      </div>
      <span
        className={
          ok
            ? "rounded-full border border-green-600/25 bg-green-500/10 px-2 py-0.5 text-xs font-medium text-green-700 dark:text-green-400"
            : "rounded-full border border-red-600/25 bg-red-500/10 px-2 py-0.5 text-xs font-medium text-red-700 dark:text-red-400"
        }
      >
        {ok ? "Set" : "Unset"}
      </span>
    </div>
  );
}

function ClipUpload({ onUploaded }: { onUploaded: () => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [saving, setSaving] = useState(false);

  async function save() {
    if (!file || !title.trim()) return;
    setSaving(true);
    try {
      await uploadCtaTemplate(file, title.trim());
      emit();
      setFile(null);
      setTitle("");
      onUploaded();
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "Upload failed");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="flex items-end gap-2">
      <div className="flex min-w-0 flex-1 flex-col gap-1.5">
        <label htmlFor="clip-title" className="text-xs font-medium">
          New clip
        </label>
        <input
          id="clip-title"
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          placeholder="Bible Focus"
          className="h-8 w-full rounded-md border bg-background px-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
        />
      </div>
      <input
        type="file"
        accept="video/mp4"
        className="hidden"
        id="clip-file"
        onChange={(event) => setFile(event.target.files?.[0] ?? null)}
      />
      <label
        htmlFor="clip-file"
        className="inline-flex h-8 shrink-0 cursor-pointer items-center gap-1.5 rounded-md border border-border bg-background px-2.5 text-sm font-medium hover:bg-muted"
      >
        <UploadCloud className="size-3.5" />
        {file ? file.name : "Choose"}
      </label>
      <Button
        onClick={() => void save()}
        disabled={saving || !file || !title.trim()}
        className="shrink-0"
      >
        {saving ? <Loader2 className="size-4 animate-spin" /> : <Rocket className="size-4" />}
        Add
      </Button>
    </div>
  );
}