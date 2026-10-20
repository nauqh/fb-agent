"use client";

import { useState } from "react";
import { CalendarClock } from "lucide-react";
import { toast } from "sonner";

import { PublishAt } from "@/components/publish-at";
import { PublishDialog } from "@/components/publish-dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { Textarea } from "@/components/ui/textarea";
import { listYoutubeBrands, scheduleJob, type YoutubeJob } from "@/lib/api/youtube";
import { pageLocalSoon } from "@/lib/format";
import { useQuery } from "@/lib/use-query";

type Network = "youtube" | "instagram";

/**
 * Schedule a produced Short to YouTube and/or Instagram through Metricool.
 *
 * A network is offered only when the brand has it connected in Metricool;
 * `off` holds what the operator unticked, so switching brand needs no reset.
 */
export function ShortsSchedule({ job, iconOnly = false }: { job: YoutubeJob; iconOnly?: boolean }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [brandId, setBrandId] = useState("");
  const [off, setOff] = useState<Network[]>([]);
  const [title, setTitle] = useState(job.raw_title ?? "");
  const [caption, setCaption] = useState("");
  const [when, setWhen] = useState(pageLocalSoon);

  const { data: brands, error } = useQuery(() => listYoutubeBrands(), [], {
    enabled: open,
    cacheKey: "shorts-brands",
  });
  const brand = brands?.find((b) => b.id === brandId) ?? brands?.[0] ?? null;
  const has = { youtube: !!brand?.channel_id, instagram: !!brand?.instagram };
  const youtube = has.youtube && !off.includes("youtube");
  const instagram = has.instagram && !off.includes("instagram");

  function toggle(network: Network, checked: boolean) {
    setOff((prev) => (checked ? prev.filter((n) => n !== network) : [...prev, network]));
  }

  async function confirm() {
    if (!brand || !(youtube || instagram)) return;
    setBusy(true);
    try {
      const result = await scheduleJob(job.id, {
        brand_id: brand.id,
        title,
        caption,
        youtube,
        instagram,
        when,
      });
      toast.success(result.draft ? "Saved as a draft in Metricool" : "Scheduled on Metricool");
      setOpen(false);
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "Could not schedule");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      {iconOnly ? (
        <Button variant="ghost" size="icon" aria-label="Schedule" onClick={() => setOpen(true)}>
          <CalendarClock className="size-4" />
        </Button>
      ) : (
        <Button variant="outline" onClick={() => setOpen(true)}>
          <CalendarClock className="size-4" />
          Schedule
        </Button>
      )}

      <PublishDialog
        open={open}
        onOpenChange={setOpen}
        busy={busy || !brand || !(youtube || instagram)}
        onConfirm={confirm}
        scheduling
      >
        {error ? (
          <p className="text-sm text-destructive">{error}</p>
        ) : !brands ? (
          <p className="text-sm text-muted-foreground">Loading brands...</p>
        ) : brands.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No Metricool brand has YouTube or Instagram connected.
          </p>
        ) : (
          <div className="flex flex-col gap-3">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="schedule-brand">Brand</Label>
              <NativeSelect id="schedule-brand" value={brand?.id ?? ""} onValueChange={setBrandId}>
                {brands.map((b) => (
                  <NativeSelectOption key={b.id} value={b.id}>
                    {b.label}
                  </NativeSelectOption>
                ))}
              </NativeSelect>
            </div>

            <div className="flex gap-4">
              {(["youtube", "instagram"] as const).map((network) => (
                <label
                  key={network}
                  className="flex cursor-pointer items-center gap-2 text-sm has-disabled:cursor-not-allowed has-disabled:opacity-50"
                  title={has[network] ? undefined : "Not connected in Metricool"}
                >
                  <input
                    type="checkbox"
                    disabled={!has[network]}
                    checked={network === "youtube" ? youtube : instagram}
                    onChange={(event) => toggle(network, event.target.checked)}
                    className="size-3.5 cursor-pointer accent-primary"
                  />
                  {network === "youtube" ? "YouTube Short" : "Instagram Reel"}
                </label>
              ))}
            </div>

            {youtube ? (
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="schedule-title">YouTube title</Label>
                <Input
                  id="schedule-title"
                  value={title}
                  maxLength={100}
                  onChange={(event) => setTitle(event.target.value)}
                />
              </div>
            ) : null}

            <div className="flex flex-col gap-1.5">
              <Label htmlFor="schedule-caption">Caption</Label>
              <Textarea
                id="schedule-caption"
                value={caption}
                placeholder={title || "Caption"}
                onChange={(event) => setCaption(event.target.value)}
              />
            </div>

            <PublishAt value={when} onChange={setWhen} />
          </div>
        )}
      </PublishDialog>
    </>
  );
}
