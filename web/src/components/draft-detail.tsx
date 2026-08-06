"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import {
  AlertTriangle,
  Check,
  ImageIcon,
  Loader2,
  RotateCcw,
  Sparkles,
  TriangleAlert,
  X,
} from "lucide-react";
import { toast } from "sonner";

import { ComposedImage } from "@/components/composed-image";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import {
  approveDraft,
  getDraft,
  listDrafts,
  recomposite,
  regenerateHero,
  rejectDraft,
  returnToReview,
  updateDraft,
} from "@/lib/api/drafts";
import { listPages } from "@/lib/api/pages";
import { chars, timeAgo, words } from "@/lib/format";
import { currentReviewFilter } from "@/lib/review-filter";
import type { Draft } from "@/lib/types";
import { useQuery } from "@/lib/use-query";
import { cn } from "@/lib/utils";

interface Form {
  hook: string;
  caption: string;
  first_comment: string;
  overlay_text: string;
  highlight_phrases: string[];
  hashtags: string[];
  image_prompt: string;
}

export function DraftDetail({ draftId }: { draftId: number }) {
  const router = useRouter();
  const [editor, setEditor] = useState<{ key: string; form: Form | null }>({
    key: "",
    form: null,
  });
  const [saving, setSaving] = useState(false);
  const [deciding, setDeciding] = useState(false);
  const [imageWork, setImageWork] = useState<"recomposite" | "hero" | null>(null);

  const { data: pages } = useQuery(() => listPages(), []);

  /**
   * The poll.
   *
   * `GET /drafts/{id}` is the poll target and the client hits it until status
   * leaves `generating`. Once the row settles the interval stops — there is
   * nothing left to watch, and a Draft under edit should not be re-read from
   * under the operator.
   */
  const { data: draft, error } = useQuery(() => getDraft(draftId), [draftId], {
    intervalMs: 900,
    pollWhile: (row) => row === null || row.status === "generating",
  });
  const generating = draft?.status === "generating";

  /**
   * Seed the editor when a different Draft is selected, or when this one
   * finishes generating and has content for the first time — and never in
   * between, because the poll keeps returning the row while it is being edited.
   *
   * Keyed and adjusted during render rather than synced in an effect: an effect
   * would render the previous Draft's text into the new Draft's boxes for one
   * frame before correcting itself.
   */
  const written = draft && draft.status !== "generating";
  const editorKey = written ? `draft:${draft.id}` : `pending:${draftId}`;
  if (editor.key !== editorKey) {
    setEditor({ key: editorKey, form: written ? toForm(draft) : null });
  }
  const form = editor.form;
  const setForm = (next: Form) => setEditor({ key: editorKey, form: next });

  const page = pages?.find((candidate) => candidate.id === draft?.page_id);
  const dirty = useMemo(
    () => (draft && form ? JSON.stringify(toForm(draft)) !== JSON.stringify(form) : false),
    [draft, form],
  );

  if (error) {
    return <Panel>Could not load draft {draftId}: {error}</Panel>;
  }
  if (!draft) {
    return (
      <div className="grid gap-6 lg:grid-cols-[340px_minmax(0,1fr)]">
        <Skeleton className="aspect-[896/1120] rounded-md" />
        <div className="space-y-4">
          <Skeleton className="h-8" />
          <Skeleton className="h-28" />
          <Skeleton className="h-40" />
        </div>
      </div>
    );
  }

  if (generating) return <Generating draft={draft} />;

  async function save() {
    if (!form) return;
    setSaving(true);
    try {
      await updateDraft(draftId, form);
      toast.success("Saved.", {
        description: "The overlay changed — recomposite to see it on the image.",
      });
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  async function decide(action: "approve" | "reject") {
    setDeciding(true);
    try {
      if (action === "approve") await approveDraft(draftId);
      else await rejectDraft(draftId);

      // Advance to whatever the queue shows next under the current filter, so
      // approving in sequence drains it without a trip back to the index.
      const remaining = await listDrafts({ status: currentReviewFilter() });
      const next = remaining.find((candidate) => candidate.id !== draftId);

      toast(action === "approve" ? `Approved — #${draftId} left the queue.` : `Rejected #${draftId}.`, {
        action: {
          label: "Undo",
          onClick: () => {
            void returnToReview(draftId).then(() => router.push(`/review/${draftId}`));
          },
        },
      });

      router.push(next ? `/review/${next.id}` : "/review");
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "Action failed");
    } finally {
      setDeciding(false);
    }
  }

  /**
   * The two image operations, priced differently on purpose.
   *
   * Recompositing redraws the panel over the hero already on disk; regenerating
   * the hero is a `google-genai` call. The columns are separate so the first one
   * is free, and the UI has to keep them apart or that distinction is decoration.
   */
  async function redoImage(kind: "recomposite" | "hero") {
    setImageWork(kind);
    try {
      if (kind === "recomposite") {
        await recomposite(draftId);
        toast.success("Recomposited from the stored hero.", {
          description: "No image generation was paid for.",
        });
      } else {
        await regenerateHero(draftId);
        toast.success("New hero generated and composited.", {
          description: "That was a paid image generation.",
        });
      }
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "Image work failed");
    } finally {
      setImageWork(null);
    }
  }

  const decided = draft.status === "approved" || draft.status === "rejected";
  /** A failed run has nothing to approve, and the server refuses it with a 409. */
  const failed = draft.status === "failed";

  return (
    <div className="grid gap-8 pb-16 lg:grid-cols-[340px_minmax(0,1fr)]">
      {/* Sticky against the detail pane's own scroll, so the image stays in
          view while the copy below it moves. */}
      <div className="space-y-3 lg:sticky lg:top-0 lg:self-start">
        {/* The real composite once one exists, and only while it is still
            current. An edited overlay makes the stored PNG stale, so the
            approximation comes back — showing a picture that no longer matches
            the copy beside it is worse than admitting it is a preview. */}
        {draft.composed_image_path && !dirty ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={`/api/media/${draft.composed_image_path}`}
            alt={`Composed image for draft ${draft.id}`}
            className="w-full rounded border"
          />
        ) : (
          <ComposedImage
            overlayText={form?.overlay_text ?? draft.overlay_text}
            highlightPhrases={form?.highlight_phrases ?? draft.highlight_phrases}
            watermarkPath={page?.watermark_image_path ?? null}
            seed={draft.id}
          />
        )}
        <div className="flex items-center justify-between text-[11px] text-muted-foreground">
          <span className="font-mono">896 × 1120</span>
          <span>
            {draft.hero_image_path ? "hero" : "no hero"}
            <span className="mx-1">·</span>
            {draft.composed_image_path ? "composed" : "not composed"}
          </span>
        </div>
        <p className="text-[11px] leading-relaxed text-muted-foreground">
          {draft.composed_image_path && !dirty
            ? "The composited PNG, measured with fontTools and rasterised by resvg."
            : dirty
              ? "Preview of your unsaved edits. Save, then Recomposite to redraw the real image."
              : "Approximate. The real panel is measured with fontTools and rasterised by resvg, so line breaks and panel height will differ."}
        </p>
        <div className="space-y-2">
          <Button
            variant="outline"
            size="sm"
            className="w-full"
            disabled={imageWork !== null || !draft.hero_image_path}
            title={
              draft.hero_image_path
                ? undefined
                : "There is no hero on disk to composite over."
            }
            onClick={() => void redoImage("recomposite")}
          >
            {imageWork === "recomposite" ? (
              <Loader2 className="size-3.5 animate-spin" />
            ) : (
              <ImageIcon className="size-3.5" />
            )}
            Recomposite
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="w-full text-muted-foreground"
            disabled={imageWork !== null}
            onClick={() => void redoImage("hero")}
          >
            {imageWork === "hero" ? (
              <Loader2 className="size-3.5 animate-spin" />
            ) : (
              <Sparkles className="size-3.5" />
            )}
            Regenerate hero
          </Button>
          <p className="text-[11px] leading-relaxed text-muted-foreground">
            Recompositing is free — it redraws the panel over the stored hero. Regenerating
            pays for a new image.
          </p>
        </div>
      </div>

      <div className="min-w-0 space-y-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="flex items-center gap-2 text-base font-medium">
              <span className="font-mono text-sm text-muted-foreground">#{draft.id}</span>
              {page?.name}
            </h2>
            <p className="pt-0.5 text-xs text-muted-foreground">
              {draft.topic ? `topic · ${draft.topic}` : `from source item ${draft.source_item_id}`}
              <span className="mx-1.5">·</span>
              {timeAgo(draft.created_at)}
            </p>
          </div>
          <span
            className={cn(
              "rounded px-2 py-1 text-xs",
              decided ? "bg-muted text-muted-foreground" : "bg-foreground/10",
            )}
          >
            {draft.status}
          </span>
        </div>

        {draft.error ? (
          <div className="space-y-2 rounded-md border border-destructive/40 bg-destructive/5 p-3">
            <p className="flex items-center gap-1.5 text-sm font-medium text-destructive">
              <TriangleAlert className="size-4" />
              Generation stopped
            </p>
            <p className="text-xs leading-relaxed text-muted-foreground">{draft.error}</p>
            <p className="text-xs text-muted-foreground">
              The row survives with its text intact, so nothing was lost silently.
            </p>
          </div>
        ) : null}

        {draft.warnings.length > 0 ? (
          <div className="space-y-1.5 rounded-md border border-gold/40 bg-gold/[0.07] p-3">
            <p className="flex items-center gap-1.5 text-sm font-medium">
              <AlertTriangle className="size-4" />
              {draft.warnings.length} rules still failing
            </p>
            <ul className="space-y-1 text-xs text-muted-foreground">
              {draft.warnings.map((warning) => (
                <li key={warning}>— {warning}</li>
              ))}
            </ul>
            <p className="pt-0.5 text-xs text-muted-foreground">
              Each was enforced and retried twice before it landed here. Your call.
            </p>
          </div>
        ) : null}

        {form ? (
          <>
            <Field
              label="Hook"
              hint={`${words(form.hook)} words · limit 65, no question`}
              flagged={words(form.hook) > 65 || form.hook.includes("?")}
            >
              <Textarea
                value={form.hook}
                rows={4}
                onChange={(event) => setForm({ ...form, hook: event.target.value })}
              />
            </Field>

            <Field
              label="Overlay text"
              hint="Rendered on the panel. Highlight phrases must appear here verbatim."
            >
              <Textarea
                value={form.overlay_text}
                rows={3}
                onChange={(event) => setForm({ ...form, overlay_text: event.target.value })}
              />
            </Field>

            <Field label="Highlight phrases" hint={`${form.highlight_phrases.length} · 5–8 expected`}>
              <div className="flex flex-wrap gap-1.5">
                {form.highlight_phrases.map((phrase) => {
                  const present = form.overlay_text.includes(phrase);
                  return (
                    <span
                      key={phrase}
                      className={cn(
                        "inline-flex items-center gap-1 rounded px-2 py-1 text-xs",
                        present
                          ? "bg-gold/20 text-foreground"
                          : "bg-destructive/10 text-destructive line-through",
                      )}
                      title={present ? undefined : "Not an exact substring — it will not render"}
                    >
                      {phrase}
                      <button
                        type="button"
                        onClick={() =>
                          setForm({
                            ...form,
                            highlight_phrases: form.highlight_phrases.filter(
                              (candidate) => candidate !== phrase,
                            ),
                          })
                        }
                        aria-label={`Remove ${phrase}`}
                      >
                        <X className="size-3" />
                      </button>
                    </span>
                  );
                })}
              </div>
              <AddPhrase
                onAdd={(phrase) =>
                  setForm({ ...form, highlight_phrases: [...form.highlight_phrases, phrase] })
                }
              />
            </Field>

            <Field
              label="Caption"
              hint={`${form.caption.split("\n").filter(Boolean).length} recap lines · max 5, each opening with an emoji`}
            >
              <Textarea
                value={form.caption}
                rows={8}
                onChange={(event) => setForm({ ...form, caption: event.target.value })}
              />
            </Field>

            <Field
              label="First comment"
              hint={`${chars(form.first_comment)} · 1,500–2,100`}
              flagged={form.first_comment.length < 1500 || form.first_comment.length > 2100}
            >
              <Textarea
                value={form.first_comment}
                rows={16}
                className="leading-relaxed"
                onChange={(event) => setForm({ ...form, first_comment: event.target.value })}
              />
            </Field>

            <Field label="Hashtags" hint={`${form.hashtags.length}`}>
              <Input
                value={form.hashtags.join(" ")}
                onChange={(event) =>
                  setForm({ ...form, hashtags: event.target.value.split(/\s+/).filter(Boolean) })
                }
                className="font-mono text-xs"
              />
            </Field>

            {/* The writer produced this, and it is what a refused hero has to be
                corrected in before paying for another one. */}
            <Field
              label="Image prompt"
              hint="Sent to Gemini for the hero. Editing it changes nothing until you regenerate."
            >
              <Textarea
                value={form.image_prompt}
                rows={5}
                className="text-xs leading-relaxed"
                onChange={(event) => setForm({ ...form, image_prompt: event.target.value })}
              />
            </Field>

            <Separator />

            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <Button variant="outline" size="sm" disabled={!dirty || saving} onClick={save}>
                  {saving ? <Loader2 className="size-3.5 animate-spin" /> : null}
                  Save changes
                </Button>
                {dirty ? (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setForm(toForm(draft))}
                    className="text-muted-foreground"
                  >
                    <RotateCcw className="size-3.5" />
                    Revert
                  </Button>
                ) : null}
              </div>

              {decided ? (
                <div className="flex items-center gap-3">
                  <p className="text-xs text-muted-foreground">
                    {draft.status === "approved"
                      ? "Approved — awaiting the Metricool push, which is v2."
                      : "Rejected."}
                  </p>
                  <Button variant="outline" size="sm" onClick={() => void returnToReview(draftId)}>
                    Return to queue
                  </Button>
                </div>
              ) : (
                <div className="flex items-center gap-2">
                  <Button
                    variant="ghost"
                    disabled={deciding}
                    onClick={() => decide("reject")}
                    className="text-muted-foreground"
                  >
                    <X className="size-4" />
                    Reject
                  </Button>
                  {failed ? (
                    <p className="text-xs text-muted-foreground">
                      This run failed, so there is nothing to approve. Reject it to clear
                      the queue, then generate again.
                    </p>
                  ) : (
                    <Button
                      className="bg-gold text-gold-foreground hover:bg-gold/90"
                      disabled={deciding}
                      onClick={() => decide("approve")}
                    >
                      {deciding ? (
                        <Loader2 className="size-4 animate-spin" />
                      ) : (
                        <Check className="size-4" />
                      )}
                      Approve
                    </Button>
                  )}
                </div>
              )}
            </div>
          </>
        ) : null}
      </div>
    </div>
  );
}

function Generating({ draft }: { draft: Draft }) {
  return (
    <div className="flex min-h-72 items-center justify-center rounded-lg border border-dashed p-10">
      <div className="w-full max-w-sm space-y-3">
        <div className="flex items-center justify-between text-sm">
          <span className="font-mono text-muted-foreground">#{draft.id}</span>
          <span className="tabular-nums text-muted-foreground">{draft.progress_pct}%</span>
        </div>
        <div className="h-1 w-full overflow-hidden rounded-full bg-border">
          <div
            className="h-full bg-gold transition-[width] duration-500"
            style={{ width: `${draft.progress_pct}%` }}
          />
        </div>
        <p className="text-center text-sm">{draft.progress_step}</p>
        <p className="text-center text-xs leading-relaxed text-muted-foreground">
          The row was inserted before generation started, so this page is polling it. Leaving
          the screen does not cancel anything.
        </p>
      </div>
    </div>
  );
}

function Field({
  label,
  hint,
  flagged,
  children,
}: {
  label: string;
  hint?: string;
  flagged?: boolean;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-2">
      <div className="flex items-baseline justify-between gap-3">
        <Label className="text-sm">{label}</Label>
        {hint ? (
          <span
            className={cn(
              "text-[11px] tabular-nums",
              flagged ? "text-destructive" : "text-muted-foreground",
            )}
          >
            {hint}
          </span>
        ) : null}
      </div>
      {children}
    </div>
  );
}

function AddPhrase({ onAdd }: { onAdd: (phrase: string) => void }) {
  const [value, setValue] = useState("");
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        if (!value.trim()) return;
        onAdd(value.trim());
        setValue("");
      }}
    >
      <Input
        value={value}
        onChange={(event) => setValue(event.target.value)}
        placeholder="Add a phrase, exactly as it appears above"
        className="h-8 text-xs"
      />
    </form>
  );
}

function Panel({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-dashed p-10 text-center text-sm text-muted-foreground">
      {children}
    </div>
  );
}

function toForm(draft: Draft): Form {
  return {
    hook: draft.hook ?? "",
    caption: draft.caption ?? "",
    first_comment: draft.first_comment ?? "",
    overlay_text: draft.overlay_text ?? "",
    highlight_phrases: [...draft.highlight_phrases],
    hashtags: [...draft.hashtags],
    image_prompt: draft.image_prompt ?? "",
  };
}
