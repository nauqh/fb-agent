"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  CalendarClock,
  ExternalLink,
  ImagePlus,
  Loader2,
  Rocket,
  RefreshCw,
  RotateCcw,
  Sparkles,
  TriangleAlert,
  X,
} from "lucide-react";
import { toast } from "sonner";

import { ComposedImage, clampInset } from "@/components/composed-image";
import { HookField } from "@/components/hook-field";
import { FacebookPreview } from "@/components/facebook-preview";
import { PublishAt } from "@/components/publish-at";
import { PublishDialog } from "@/components/publish-dialog";
import { KIND_GLYPH, KIND_LABEL } from "@/components/source-card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import {
  getDraft,
  publishDraft,
  publishMode,
  regenerateField,
  regenerateHero,
  rejectDraft,
  removeInset,
  returnToReview,
  updateDraft,
  uploadInset,
} from "@/lib/api/drafts";
import { getPageLayout, type ResolvedLayout } from "@/lib/api/layout";
import { listPages } from "@/lib/api/pages";
import { getNextSlot, type NextSlot } from "@/lib/api/schedule";
import { getSourceItem } from "@/lib/api/sources";
import { chars, pageLocalSoon, timeAgo, words } from "@/lib/format";
import type { RegeneratableField, RewriteProposal } from "@/lib/api/drafts";
import type { Draft } from "@/lib/types";
import { useQuery } from "@/lib/use-query";
import { pageAvatarRaw } from "@/lib/page-avatar";
import { cn } from "@/lib/utils";

type View = "edit" | "preview";

interface Form {
  hook: string;
  caption: string;
  first_comment: string;
  highlight_phrases: string[];
  image_prompt: string;
  /** Null means "the default", which is what the server stores for an untouched draft. */
  inset_size_px: number | null;
  inset_x_ratio: number | null;
  inset_y_ratio: number | null;
  /**
   * The ring. Null is "the Page's", `0` is "no ring" — two different answers,
   * which is why the controls below have an explicit way back to null rather
   * than treating the Page's current value as the off position.
   */
  inset_border_width_px: number | null;
  inset_border_color: string | null;
  /** `card` or `full_overlay` for this draft. Null follows the Page. */
  template: "card" | "full_overlay" | null;
}

export function DraftDetail({
  draftId,
  onDecided,
}: {
  draftId: number;
  /** Close the drawer. Supplied by `DraftSheet` so a decision animates out the
   *  same way a dismissal does. */
  onDecided?: () => void;
}) {
  const router = useRouter();
  const [editor, setEditor] = useState<{ key: string; form: Form | null }>({
    key: "",
    form: null,
  });
  const [saving, setSaving] = useState(false);
  const [deciding, setDeciding] = useState(false);
  const [imageWork, setImageWork] = useState<"hero" | "inset" | null>(null);
  const [view, setView] = useState<View>("edit");
  const filePicker = useRef<HTMLInputElement>(null);

  const { data: pages } = useQuery(() => listPages(), []);

  /**
   * The poll.
   *
   * `GET /drafts/{id}` is the poll target and the client hits it until status
   * leaves `generating`. Once the row settles the interval stops — there is
   * nothing left to watch, and a Draft under edit should not be re-read from
   * under the operator.
   */
  const { data: draft, error, refresh } = useQuery(() => getDraft(draftId), [draftId], {
    intervalMs: 900,
    pollWhile: (row) => row === null || row.status === "generating",
  });
  const generating = draft?.status === "generating";

  /**
   * This Page's layout, which the preview and the inset slider are both drawn
   * from.
   *
   * Fetched rather than taken from a constant. `ComposedImage` used to read a
   * hand-kept copy of `layout.yml` with no per-Page values in it, so every
   * override on Global — the four paddings, the type size, the panel colour,
   * the template — moved the card on Global and moved nothing here.
   *
   * Keyed on the *draft's* Page, not the switcher's. The drawer can be opened
   * from a queue that was scoped when it loaded, and drawing one Page's draft
   * with another Page's layout is exactly the class of bug this replaces.
   */
  const { data: layoutResult } = useQuery(
    () => getPageLayout(draft!.page_id),
    [draft?.page_id],
    { enabled: draft != null },
  );
  const layout = layoutResult?.layout ?? null;

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

  /**
   * A rewrite came back. It goes in the boxes, not in the database.
   *
   * **Rewrite proposes, Save writes, Revert undoes** — the same three words that
   * describe typing in the box by hand, which is the point. The old shape had
   * the server write the field and the screen re-read it, and the screen did not
   * re-read it: the editor re-seeds on a key change and the key is the draft's
   * id, so a rewrite left `form` holding the pre-rewrite text over a row that
   * had moved. Both halves of the screen showed the old text — the preview draws
   * `form.hook ?? draft.hook` — while the toast said it had been rewritten, the
   * draft went dirty against text nobody typed, and pressing the **Save changes**
   * that appeared wrote the old text back over the new. Every press was a paid
   * Gemini call undone by the one visible affordance after it (client feedback
   * A2, 2026-08-14).
   *
   * Putting the proposal in the form instead makes all of that impossible rather
   * than fixed: there is no second copy to disagree with, `dirty` is true
   * because something really did change, and the undo the operator wanted is the
   * Revert button that was already there.
   *
   * The phrases must move with the hook. They are verbatim substrings of it, so
   * keeping the old ones would render no gold at all.
   */
  function applyProposal(proposal: RewriteProposal) {
    if (!form) return;
    setForm({
      ...form,
      [proposal.field]: proposal.text,
      ...(proposal.highlight_phrases
        ? { highlight_phrases: proposal.highlight_phrases }
        : {}),
    });
  }

  const page = pages?.find((candidate) => candidate.id === draft?.page_id);
  const dirty = useMemo(
    () => (draft && form ? JSON.stringify(toForm(draft)) !== JSON.stringify(form) : false),
    [draft, form],
  );

  /**
   * Drag the circle, or click anywhere on the card to put it there — the same
   * gesture the old app had (`circular-inset-dialog.tsx:360-372`), where a press
   * both moves the inset and begins the drag.
   *
   * **On `window`, not on the card.** The obvious version — `onPointerMove` on
   * the card, with `setPointerCapture` — receives exactly one move and then goes
   * silent, verified with a counter in the handler: the press lands, the first
   * move lands, and every move after it stops reaching the element even though
   * the pointer never leaves it and capture reports as held. Listening on the
   * window sidesteps whatever swallows them, and it is the more correct place
   * anyway: a drag that continues off the edge of the card is still that drag.
   *
   * Above the early returns because hooks cannot be conditional; the effect does
   * nothing until a press sets `dragging`.
   */
  const [dragging, setDragging] = useState(false);
  const cardRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!dragging) return;

    const move = (event: PointerEvent) => {
      const box = cardRef.current?.getBoundingClientRect();
      if (!box) return;
      // Updated from the previous state rather than from `form` in scope, so
      // the listeners do not have to be torn down and rebuilt on every frame of
      // the drag — and cannot write back a form from before it started.
      setEditor((prev) =>
        prev.form
          ? {
              ...prev,
              form: {
                ...prev.form,
                inset_x_ratio: clamp01((event.clientX - box.left) / box.width),
                inset_y_ratio: clamp01((event.clientY - box.top) / box.height),
              },
            }
          : prev,
      );
    };
    const stop = () => setDragging(false);

    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", stop);
    window.addEventListener("pointercancel", stop);
    return () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", stop);
      window.removeEventListener("pointercancel", stop);
    };
  }, [dragging]);

  if (error) {
    return <Panel>Could not load draft {draftId}: {error}</Panel>;
  }
  if (!draft) return <DetailSkeleton />;

  if (generating) return <Generating draft={draft} />;

  // The layout and the Page are what the card is drawn from, and neither has a
  // safe stand-in: a default layout is a second copy of `layout.yml`, and a
  // missing Page means no watermark decision. Both are one fast read that
  // starts as soon as the draft lands, so this is a flicker, not a wait.
  if (!layout || !page) return <DetailSkeleton />;

  async function save() {
    if (!form) return;
    setSaving(true);
    try {
      await updateDraft(draftId, form);
      toast.success("Saved.", {
        description: "The image was redrawn to match.",
      });
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  /** Reject: the one decision that is not publishing. Approve is gone — see
   *  the footer for why. */
  async function reject() {
    setDeciding(true);
    try {
      // A decision closes the drawer, and the form goes with it. Anything typed
      // and not saved would be silently discarded — including a highlight,
      // which is the one edit whose whole feedback is the picture and so is the
      // easiest to believe is already stored. Rejecting saves too: it is
      // reversible, and a draft that comes back should come back as it looked.
      if (dirty && form) await updateDraft(draftId, form);
      await rejectDraft(draftId);

      toast("Rejected.", {
        action: {
          label: "Undo",
          onClick: () => {
            // Puts the row back in the queue and leaves it there. Reopening the
            // drawer would undo the decision *and* the dismissal, which is one
            // more thing than was asked for.
            void returnToReview(draftId);
          },
        },
      });

      // Back to the queue, never on to the next draft. Deciding one thing
      // should not open another — the row leaving the list is the feedback, and
      // the operator picks what to look at next.
      if (onDecided) onDecided();
      else router.push("/review");
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "Action failed");
    } finally {
      setDeciding(false);
    }
  }

  /**
   * The only operation left that costs anything.
   *
   * Redrawing the panel is free and now happens on save; buying a hero is a
   * `google-genai` call, so it stays a button the operator presses on purpose.
   * The inset below it is free — an upload, not a generation.
   */
  async function redoImage(kind: "hero") {
    setImageWork(kind);
    try {
      await regenerateHero(draftId);
      toast.success("New hero generated and composited.", {
        description: "That was a paid image generation.",
      });
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "Image work failed");
    } finally {
      setImageWork(null);
    }
  }

  /**
   * Put a picture in the circle, or take it out. `null` removes.
   *
   * Immediate rather than staged into the form like the slider is, because a
   * `File` is not something the form can hold and save later — and the server
   * redraws the card in the same call, so the picture beside this button is
   * correct the moment it returns. `refresh` is what pulls the new row: the
   * poll has already stopped by the time a draft is reviewable.
   */
  async function changeInset(file: File | null) {
    setImageWork("inset");
    try {
      // Save first, and this is the fix for a bug that survived the rewrite.
      // The server redraws the card from the **row**; the preview above draws
      // from the form. So uploading with an unsaved highlight baked the *old*
      // gold into the PNG while the preview kept showing the new gold — two
      // pictures that disagree, with nothing on screen saying so. Publish then
      // ships the PNG. Intermittent in exactly the way it was reported: it
      // depended on whether a Save happened to land before the upload.
      if (dirty && form) await updateDraft(draftId, form);

      if (file) await uploadInset(draftId, file);
      else await removeInset(draftId);
      await refresh();
      toast.success(file ? "Inset added." : "Inset removed.");
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "Inset failed");
    } finally {
      setImageWork(null);
    }
  }

  const decided = draft.status === "approved" || draft.status === "rejected";
  /** A failed run has nothing to approve, and the server refuses it with a 409. */
  const failed = draft.status === "failed";

  /**
   * The hero with the panel drawn over it, never the baked PNG.
   *
   * Showing the composited file is what made an edit require a round trip: the
   * PNG cannot know about a highlight you added a second ago. Drawing the panel
   * here instead makes it instant, and costs nothing — the hero is the
   * expensive half and it is already on disk.
   *
   * The server bakes the same thing into the PNG when the draft is saved.
   *
   * Held as a value because both views draw it: on its own under Edit, and
   * inside the feed card under Preview.
   */
  const picture = (
    <ComposedImage
      layout={
        // The draft's own form laid over the Page's, so the toggle moves the
        // card as it is clicked rather than after a save. Same merge the server
        // does in `layout_for.resolve_draft`.
        form?.template && form.template !== layout.template
          ? { ...layout, template: form.template }
          : layout
      }
      page={page}
      overlayText={form?.hook ?? draft.hook}
      highlightPhrases={form?.highlight_phrases ?? draft.highlight_phrases}
      heroSrc={draft.hero_image_url}
      insetSrc={draft.inset_image_url}
      // From the form, not the row: the slider and the drag have to move the
      // circle as they happen, which is the only way to choose either.
      insetSizePx={form?.inset_size_px ?? draft.inset_size_px}
      insetXRatio={form ? form.inset_x_ratio : draft.inset_x_ratio}
      insetYRatio={form ? form.inset_y_ratio : draft.inset_y_ratio}
      insetBorderWidthPx={
        form ? form.inset_border_width_px : draft.inset_border_width_px
      }
      insetBorderColor={form ? form.inset_border_color : draft.inset_border_color}
      seed={draft.id}
    />
  );

  // No bottom padding of its own — the drawer supplies it. This carried
  // `pb-16` from when the detail was a full page needing clearance above the
  // viewport edge, which inside the drawer was just dead space under Approve.
  return (
    <div className="space-y-6">
      {/* Just what the draft is. The status pill, the topic and the age all
          lived here and all of them are already in the row you clicked to get
          here — repeating them costs a line and tells you nothing new.
          `pr-10` keeps the heading clear of the drawer's close button. */}
      <h2 className="pr-10 text-base font-medium">{page?.name}</h2>

      <SourceLine draft={draft} />

      {draft.error ? (
        <div className="space-y-2 rounded-md border border-destructive/40 bg-destructive/5 p-3">
          <p className="flex items-center gap-1.5 text-sm font-medium text-destructive">
            <TriangleAlert className="size-4" />
            Generation stopped
          </p>
          <p className="text-xs leading-relaxed text-muted-foreground">{draft.error}</p>
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
        </div>
      ) : null}


      {/* Edit and Preview are separate views, as they were in the old
          app. The preview is a whole post and was cramped into a 340px
          column; given the full width it can put the feed post and the
          first comment side by side, which is how they are read. */}
      <Tabs value={view} onValueChange={(next) => setView(next as View)}>
        <TabsList className="gap-1.5 p-1 *:min-w-28 *:px-4">
          <TabsTrigger value="edit">Edit</TabsTrigger>
          <TabsTrigger value="preview">Preview</TabsTrigger>
        </TabsList>

        <TabsContent value="edit" className="mt-6">
          <div className="grid gap-8 lg:grid-cols-[340px_minmax(0,1fr)]">
            {/* Sticky against the pane's own scroll, so the image stays in
                view while the copy beside it moves. */}
            <div className="space-y-3 lg:sticky lg:top-0 lg:self-start">
              <div
                className={cn(
                  "overflow-hidden rounded border",
                  // `touch-none` or a drag on a phone scrolls the drawer
                  // instead of moving the circle.
                  draft.inset_image_path && "cursor-crosshair touch-none",
                )}
                ref={cardRef}
                onPointerDown={(event) => {
                  // The press is itself a placement, so a click puts the circle
                  // where you clicked without any dragging at all. The window
                  // listeners take it from here.
                  if (!draft.inset_image_path || !form) return;
                  event.preventDefault();
                  const box = event.currentTarget.getBoundingClientRect();
                  setForm({
                    ...form,
                    inset_x_ratio: clamp01((event.clientX - box.left) / box.width),
                    inset_y_ratio: clamp01((event.clientY - box.top) / box.height),
                  });
                  setDragging(true);
                }}
              >
                {picture}
              </div>
              <div className="flex items-center justify-between text-[11px] text-muted-foreground">
                <span className="font-mono">896 × 1120</span>
                <span>
                  {draft.hero_image_path ? "hero" : "no hero"}
                  <span className="mx-1">·</span>
                  {draft.composed_image_path ? "composed" : "not composed"}
                </span>
              </div>
              {/* The picture above is always current, so nothing here is about
                  what you are looking at — only about whether the *file* on
                  disk matches it yet. */}
              {!draft.hero_image_path ? (
                <p className="text-[11px] text-muted-foreground">
                  No hero yet — the background is a placeholder.
                </p>
              ) : dirty || !draft.composed_image_path ? (
                <p className="text-[11px] text-muted-foreground">
                  Save to bake this into the published PNG.
                </p>
              ) : null}
          {/* Recomposite used to sit here. Saving now redraws the panel
              server-side, so the button only ever repeated what Save had
              already done — and left the PNG stale for anyone who did not
              know to press it. */}
          <Button
            variant="outline"
            size="sm"
            className="w-full"
            disabled={imageWork !== null}
            onClick={() => void redoImage("hero")}
            // The one button that spends money. Said on hover rather than in a
            // paragraph under it — the warning belongs on the trigger.
            title="Buys a new image from Gemini."
          >
            {imageWork === "hero" ? (
              <Loader2 className="size-3.5 animate-spin" />
            ) : (
              <Sparkles className="size-3.5" />
            )}
            Regenerate hero
          </Button>
          {/* Which of the two forms this card is drawn in. Under the picture
              because that is the only place the difference is visible: the
              choice depends on the photograph, not on the brand — a busy shot
              with a face low in the frame is ruined by a panel lying over it,
              and the same panel is the making of a wide landscape.

              Null follows the Page, so a draft nobody has touched still moves
              when the Page's form changes. Once set it is this draft's. */}
          {form ? (
            <div className="space-y-2 rounded-md border p-3">
              <div className="flex items-baseline justify-between">
                <Label className="text-xs">Card form</Label>
                <span className="text-[11px] text-muted-foreground">
                  {form.template === null ? "from Page" : "this draft"}
                </span>
              </div>
              <div className="flex gap-1">
                {(["card", "full_overlay"] as const).map((option) => {
                  const shown = form.template ?? layout.template;
                  return (
                    <button
                      key={option}
                      type="button"
                      onClick={() => setForm({ ...form, template: option })}
                      className={cn(
                        "flex-1 rounded-md border px-2 py-1 text-[11px] capitalize transition-colors",
                        option === shown
                          ? "border-primary bg-primary/10 text-primary"
                          : "text-muted-foreground hover:bg-muted",
                      )}
                    >
                      {option.replace(/_/g, " ")}
                    </button>
                  );
                })}
                {form.template !== null ? (
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-auto px-2 text-[11px] text-muted-foreground"
                    onClick={() => setForm({ ...form, template: null })}
                  >
                    Use the Page&rsquo;s
                  </Button>
                ) : null}
              </div>
            </div>
          ) : null}

          {/* The inset sits under the picture rather than in the copy column:
              it is the one control whose whole feedback is the image, and the
              slider is useless without it in view. */}
          <div className="space-y-2 rounded-md border p-3">
            <div className="flex items-baseline justify-between">
              <Label className="text-xs">Circular inset</Label>
              <span className="text-[11px] tabular-nums text-muted-foreground">
                {draft.inset_image_path
                  ? `${clampInset(form?.inset_size_px, layout)}px`
                  : "none"}
              </span>
            </div>

            {draft.inset_image_path && form ? (
              // Free and instant: the preview redraws as it moves, and Save
              // bakes it into the PNG like every other edit.
              <>
                <input
                  type="range"
                  className="w-full accent-foreground"
                  // The Page's own bounds, not the file's. `portrait.min_px`
                  // and `max_width_ratio` are both overridable, and a slider
                  // running to a diameter the compositor would clamp is a
                  // control that lies about what it is set to.
                  min={layout.portrait.min_px}
                  max={Math.round(
                    layout.image.width * layout.portrait.max_width_ratio,
                  )}
                  step={2}
                  value={clampInset(form.inset_size_px, layout)}
                  onChange={(event) =>
                    setForm({ ...form, inset_size_px: Number(event.target.value) })
                  }
                />
                <p className="text-[11px] text-muted-foreground">
                  Drag the circle on the image, or click where you want it.
                </p>

                <InsetRing layout={layout} form={form} onChange={setForm} />
              </>
            ) : (
              <p className="text-[11px] leading-relaxed text-muted-foreground">
                Upload a picture to put a circle on the seam. Nothing generates
                this one.
              </p>
            )}

            <div className="flex gap-1">
              <Button
                variant="outline"
                size="sm"
                className="flex-1"
                disabled={imageWork !== null}
                onClick={() => filePicker.current?.click()}
              >
                {imageWork === "inset" ? (
                  <Loader2 className="size-3.5 animate-spin" />
                ) : (
                  <ImagePlus className="size-3.5" />
                )}
                {draft.inset_image_path ? "Replace" : "Upload"}
              </Button>
              {draft.inset_image_path ? (
                <>
                  {/* Back to the seam. Nulls rather than the ratios it would
                      resolve to, because the seam moves with the panel and a
                      number pinned today is wrong after the next hook edit. */}
                  {form && (form.inset_x_ratio !== null || form.inset_y_ratio !== null) ? (
                    <Button
                      variant="ghost"
                      size="sm"
                      className="text-muted-foreground"
                      onClick={() =>
                        setForm({ ...form, inset_x_ratio: null, inset_y_ratio: null })
                      }
                    >
                      Reset
                    </Button>
                  ) : null}
                  <Button
                    variant="ghost"
                    size="sm"
                    className="text-muted-foreground"
                    disabled={imageWork !== null}
                    onClick={() => void changeInset(null)}
                  >
                    Remove
                  </Button>
                </>
              ) : null}
            </div>

            <input
              ref={filePicker}
              type="file"
              accept="image/*"
              className="hidden"
              onChange={(event) => {
                const file = event.target.files?.[0];
                // Cleared so picking the same file twice still fires a change.
                event.target.value = "";
                if (file) void changeInset(file);
              }}
            />
          </div>
            </div>

            <div className="min-w-0 space-y-6">
              {form ? (
                <>
                <Field
                  label="Hook"
                  regenerate={
                    <Regenerate
                      draftId={draftId}
                      field="hook"
                      label="Hook"
                      form={form}
                      onProposal={applyProposal}
                    />
                  }
                  hint={`${words(form.hook)} words · on the image · limit 65, no question`}
                  flagged={words(form.hook) > 65 || form.hook.includes("?")}
                >
                  {/* Select the words and press the button. The chips this replaced
                      asked the operator to retype text already on screen, exactly,
                      and a phrase off by one character renders nothing. */}
                  <HookField
                    value={form.hook}
                    phrases={form.highlight_phrases}
                    onChange={(hook) => setForm({ ...form, hook })}
                    onPhrasesChange={(highlight_phrases) =>
                      setForm({ ...form, highlight_phrases })
                    }
                  />
                </Field>

                <Field
                  label="Caption"
                  regenerate={
                    <Regenerate
                      draftId={draftId}
                      field="caption"
                      label="Caption"
                      form={form}
                      onProposal={applyProposal}
                    />
                  }
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
                  regenerate={
                    <Regenerate
                      draftId={draftId}
                      field="first_comment"
                      label="First comment"
                      form={form}
                      onProposal={applyProposal}
                    />
                  }
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

                </>
              ) : null}
            </div>
          </div>
        </TabsContent>

        <TabsContent value="preview" className="mt-6">
          <FacebookPreview
            pageName={page?.name ?? "Page"}
            avatarPath={page ? pageAvatarRaw(page) : null}
            image={picture}
            caption={form?.caption ?? draft.caption ?? ""}
            firstComment={form?.first_comment ?? draft.first_comment ?? ""}
          />
        </TabsContent>
      </Tabs>

      <Separator />

      {/* Outside the tabs: a decision is about the draft, not about the
          view you happen to be looking at, so Approve is reachable from
          the preview too. */}
      {/* One height for everything in it. The publish field is 32px and the
          decision buttons were the default 36px, which left the row stepped and
          the field's baseline floating between them. `size="sm"` throughout is
          what makes it read as one strip rather than three groups. */}
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

        {/* Reject, then the three ways to publish. **Approve is gone**: it set
            a status that took the row out of the queue and did nothing else,
            was reversible, and was never required by publish — a step with no
            consequence in front of the one step that cannot be taken back. The
            client asked whether it was needed; it was not.

            `DraftStatus.APPROVED` still exists for the rows that already carry
            it, and `returnToReview` still brings one back. Nothing writes it
            any more. */}
        <div className="flex items-center gap-2">
          {decided ? (
            <>
              <p className="mr-1 text-xs text-muted-foreground">
                {draft.status === "approved" ? "Approved." : "Rejected."}
              </p>
              <Button
                variant="outline"
                size="sm"
                onClick={() => void returnToReview(draftId)}
              >
                Return to queue
              </Button>
            </>
          ) : (
            <Button
              variant="ghost"
              size="sm"
              disabled={deciding}
              onClick={() => void reject()}
              className="text-muted-foreground"
            >
              <X className="size-4" />
              Reject
            </Button>
          )}
          {failed ? (
            <p className="text-xs text-muted-foreground">
              Failed — there is nothing to publish.
            </p>
          ) : (
            <PublishAction draft={draft} onPublished={refresh} />
          )}
        </div>
      </div>
    </div>
  );
}

/**
 * Publish, from inside the drawer.
 *
 * The queue's row menu has always had this; the drawer is where the operator
 * actually reads the post, and having to close it and find the row again to
 * send what they just read was a step with no purpose. The old app offered both
 * for the same reason — `draft-review-row.tsx:1000` in the row menu and `:1390`
 * in the sheet footer, from one handler.
 *
 * Shown for a decided draft too, unlike Reject and Approve. Approved *is* the
 * state a draft is published from, and the server never required it
 * (`routes/drafts.py:361` refuses only a republish, a FAILED row, and one with
 * no composite) — the disabled conditions here are those three and nothing
 * more, so the button is never offered for a call that would 409.
 *//**
 * The three ways a draft leaves the queue: now, at a time, or at the next free
 * slot.
 *
 * **Approve is gone, and the client was right about why.** It set
 * `status = approved`, which took the row out of the Review queue and did
 * nothing else — reversible by `unapprove`, and never required by publish,
 * which refuses only a republish, a FAILED draft and one with no composite. So
 * it was a queue movement with no consequence sitting in front of the action
 * that has every consequence. These three replace it.
 *
 * "Schedule next available" asks the server, which walks this Page's configured
 * times against Metricool's planner. That read is the only authority on what is
 * taken (ADR-0001) — a post scheduled by hand in Metricool's own UI occupies a
 * slot exactly as much as one of ours.
 *
 * All three land in the same confirmation, because the irreversible part is
 * identical: once Metricool has it, it goes to a page with an audience on a
 * schedule we no longer own.
 */
function PublishAction({
  draft,
  onPublished,
}: {
  draft: Draft;
  onPublished: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [when, setWhen] = useState(pageLocalSoon);
  const [slot, setSlot] = useState<NextSlot | null>(null);
  const [finding, setFinding] = useState(false);
  // Whether this deployment publishes for real. Undefined until it answers —
  // treated as "no claim" below rather than as either mode, because guessing
  // wrong in the reassuring direction is the bug this is here to fix.
  const { data: mode } = useQuery(() => publishMode(), []);

  if (draft.metricool_post_id) {
    return (
      <p className="text-xs text-muted-foreground">
        In Metricool — change it in the planner.
      </p>
    );
  }

  const blocked = draft.status === "failed" || !draft.composed_image_path;

  /** `undefined` means "as soon as Metricool will take it" — Publish now. */
  async function publish(at: string | undefined) {
    setBusy(true);
    try {
      await publishDraft(draft.id, at);
      toast(
        mode?.rehearsal
          ? "Handed to Metricool as a draft. It will not publish."
          : "Handed to Metricool.",
      );
      onPublished();
      setOpen(false);
      setSlot(null);
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "Publish failed");
    } finally {
      setBusy(false);
    }
  }

  /**
   * Ask for the next free slot, then confirm it by name.
   *
   * Fetched on the click rather than held on the screen: it depends on the
   * planner, which anyone can change from Metricool, so a value shown since the
   * drawer opened would be a guess by the time it was used.
   */
  async function findSlot() {
    setFinding(true);
    try {
      const found = await getNextSlot(draft.page_id);
      setSlot(found);
      setWhen(found.when.slice(0, 16));
      setOpen(true);
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "No slot available");
    } finally {
      setFinding(false);
    }
  }

  return (
    <>
      <PublishAt value={when} onChange={setWhen} />

      {/* Schedule — the time beside it is the one that goes out. */}
      <Button
        variant="outline"
        size="sm"
        disabled={blocked}
        onClick={() => {
          setSlot(null);
          setOpen(true);
        }}
      >
        <CalendarClock className="size-4" />
        Schedule
      </Button>

      <Button
        variant="outline"
        size="sm"
        disabled={blocked || finding}
        onClick={() => void findSlot()}
        title="The next configured publishing time with nothing already queued at it."
      >
        {finding ? (
          <Loader2 className="size-4 animate-spin" />
        ) : (
          <CalendarClock className="size-4" />
        )}
        Next slot
      </Button>

      {/* Publish now is the primary of the three: it is what the operator
          reaches for on a post that is ready, and the other two are the
          deliberate detours. */}
      <Button
        size="sm"
        className="bg-gold text-gold-foreground hover:bg-gold/90"
        disabled={blocked}
        onClick={() => {
          setSlot(null);
          setWhen("");
          setOpen(true);
        }}
      >
        <Rocket className="size-4" />
        Publish now
      </Button>

      <PublishDialog
        open={open}
        onOpenChange={setOpen}
        busy={busy}
        onConfirm={() => void publish(when || undefined)}
      >
        <p className="text-sm text-muted-foreground">
          {slot ? (
            <>
              The next free slot is <strong>{slot.label}</strong> on{" "}
              {slot.when.slice(0, 10)}.
              {slot.taken > 0
                ? ` ${slot.taken} earlier slot${slot.taken === 1 ? "" : "s"} already had a post.`
                : ""}
            </>
          ) : when ? (
            <>It will go out at the time in the field, GMT+7.</>
          ) : (
            <>It will go out as soon as Metricool will take it.</>
          )}
        </p>

        {/* Said before the press, because there is no undo after it. Only when
            rehearsal is on: a warning shown in both modes is one nobody reads,
            and publishing for real is what the button already claims to do. */}
        {mode?.rehearsal ? (
          <p className="text-sm font-medium text-amber-700 dark:text-amber-400">
            Rehearsal mode. This lands in the planner as a draft and will not
            reach the page — the time above is when it would have gone out.
          </p>
        ) : null}
      </PublishDialog>
    </>
  );
}

/** The old app's ceiling (`MAX_INSET_BORDER_WIDTH_PX`), and the API's clamp. */
const MAX_INSET_BORDER_PX = 48;

/**
 * The ring around the disc: how thick, and what colour.
 *
 * Per draft, over the Page's defaults on Global, because the right ring depends
 * on the picture inside the circle rather than on the brand — a dark portrait
 * wants a light ring to lift it off the panel, a bright one usually wants none.
 * The old app had both here for the same reason
 * (`circular-inset-dialog.tsx:608-680`).
 *
 * **Null and zero are different answers, and the UI has to keep them apart.**
 * Null means "whatever the Page is set to" and follows it when that changes;
 * zero means this draft has chosen to have no ring. So the slider cannot be the
 * only control — sliding to 0 would be indistinguishable from inheriting a Page
 * whose default happens to be 0 — hence the explicit "Use the Page's" reset,
 * which is the only way back to null once either has been touched.
 */
function InsetRing({
  layout,
  form,
  onChange,
}: {
  layout: ResolvedLayout;
  form: Form;
  onChange: (next: Form) => void;
}) {
  const inherited =
    form.inset_border_width_px === null && form.inset_border_color === null;
  const width = form.inset_border_width_px ?? layout.portrait.border_width_px;
  const colour = form.inset_border_color ?? layout.portrait.border_color;

  return (
    <div className="space-y-2 border-t pt-2">
      <div className="flex items-baseline justify-between gap-2">
        <Label className="text-xs">Ring</Label>
        <span className="text-[11px] tabular-nums text-muted-foreground">
          {width === 0 ? "none" : `${width}px`}
          {inherited ? " · from Page" : ""}
        </span>
      </div>

      <input
        type="range"
        className="w-full accent-foreground"
        min={0}
        max={MAX_INSET_BORDER_PX}
        step={1}
        value={width}
        onChange={(event) =>
          onChange({
            ...form,
            inset_border_width_px: Number(event.target.value),
            // The colour comes along the moment the width is touched, so the
            // draft stops tracking the Page on both at once. Leaving the colour
            // null here makes a draft that follows the Page's colour and not
            // its width, which is a state nobody asked for and cannot be seen.
            inset_border_color: form.inset_border_color ?? colour,
          })
        }
      />

      <div className="flex items-center gap-2">
        <input
          type="color"
          value={colour}
          aria-label="Ring colour"
          // Disabled at zero rather than hidden: the control keeping its place
          // is what says the colour is still there and simply has nothing to
          // paint, instead of the row appearing to lose a setting.
          disabled={width === 0}
          onChange={(event) =>
            onChange({
              ...form,
              inset_border_color: event.target.value,
              inset_border_width_px: form.inset_border_width_px ?? width,
            })
          }
          className="size-7 shrink-0 cursor-pointer rounded border bg-transparent disabled:opacity-40"
        />
        <Input
          value={colour}
          disabled={width === 0}
          aria-label="Ring colour hex"
          onChange={(event) =>
            onChange({
              ...form,
              inset_border_color: event.target.value,
              inset_border_width_px: form.inset_border_width_px ?? width,
            })
          }
          className="h-7 w-24 font-mono text-[11px]"
        />
        {inherited ? null : (
          <Button
            variant="ghost"
            size="sm"
            className="h-7 px-2 text-[11px] text-muted-foreground"
            onClick={() =>
              onChange({
                ...form,
                inset_border_width_px: null,
                inset_border_color: null,
              })
            }
          >
            Use the Page&rsquo;s
          </Button>
        )}
      </div>
    </div>
  );
}

/**
 * Ask the writer for one field again, optionally saying how.
 *
 * Sits directly above its own field rather than in the footer, because it acts
 * on *this* field and a row of three identical buttons somewhere else would not
 * say which. The old app put it in the same place
 * (`regenerate-field-control.tsx`).
 *
 * **The box is always visible, not behind a toggle.** The client asked for it in
 * as many words — *"should there be a textbox for me to input how I want it to
 * be changed"* — after pressing the unargued button on a hook that was too short
 * and getting another short hook. Nothing in `validators.py` sets a minimum
 * length, so the button alone can only re-roll, never steer; a control hidden
 * behind a chevron would leave them pressing the same button. Empty is the
 * common case and is still one click.
 *
 * **Writes nothing.** It used to save the whole form first, because the server
 * read the kept fields off the row — so pressing Rewrite on the hook silently
 * committed an unsaved caption. The kept fields are sent from the form now, and
 * the result comes back as a proposal for the editor to hold.
 */
function Regenerate({
  draftId,
  field,
  label,
  form,
  onProposal,
}: {
  draftId: number;
  field: RegeneratableField;
  label: string;
  form: Form | null;
  /** Put the writer's text in the boxes. Saving it is the operator's press —
   *  see `applyProposal`. */
  onProposal: (proposal: RewriteProposal) => void;
}) {
  const [busy, setBusy] = useState(false);
  // Kept after a press, not cleared: "make it longer" is usually said twice, and
  // the box is on screen, so nothing is being reused invisibly. It is never sent
  // to the row — an instruction describes an action, not the post.
  const [instruction, setInstruction] = useState("");

  async function run() {
    setBusy(true);
    try {
      // What the new field has to fit is what is on screen, so the kept fields
      // are sent from the form — unsaved edits included. This is what lets the
      // press write nothing at all: the server used to read them off the row,
      // which is why the screen had to save first.
      const proposal = await regenerateField(draftId, field, {
        keeping: form
          ? { hook: form.hook, caption: form.caption, first_comment: form.first_comment }
          : undefined,
        instruction: instruction.trim() || undefined,
      });
      onProposal(proposal);
      toast.success(`New ${label.toLowerCase()}.`, {
        description: "Not saved yet — Save changes keeps it, Revert throws it away.",
      });
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "Could not rewrite that");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex items-center gap-2">
      <Input
        value={instruction}
        disabled={busy}
        placeholder={`How should the ${label.toLowerCase()} change? Optional.`}
        onChange={(event) => setInstruction(event.target.value)}
        // Enter runs it. The box is one line and has no other action, and the
        // draft form below is saved by its own button, so nothing else can be
        // submitted by accident.
        onKeyDown={(event) => {
          if (event.key === "Enter") {
            event.preventDefault();
            void run();
          }
        }}
        maxLength={500}
        className="h-7 text-xs"
      />
      <button
        type="button"
        onClick={() => void run()}
        disabled={busy}
        title={`Ask the writer for a new ${label.toLowerCase()}, keeping the other fields.`}
        className="inline-flex shrink-0 items-center gap-1 rounded px-1.5 py-1 text-[11px] font-normal text-muted-foreground transition-colors hover:bg-muted hover:text-foreground disabled:opacity-50"
      >
        {busy ? (
          <Loader2 className="size-3 animate-spin" />
        ) : (
          <RefreshCw className="size-3" />
        )}
        Rewrite
      </button>
    </div>
  );
}

/**
 * Which Source Item this draft was written from.
 *
 * Client feedback G2 (2026-08-16): *"I have no idea which source or which
 * competitor posts the tool gens content from."* Nothing was missing from the
 * data — 35 of the 38 drafts in the database carry a `source_item_id`, and it
 * has been on the wire since the first day. It was missing from every screen.
 *
 * **In the drawer, not on the queue row.** `useQuery` re-runs on every store
 * notification, so a hook per row would turn one save into N requests against a
 * queue of any length. The drawer is also where the question is actually asked,
 * with the copy it produced next to it.
 *
 * Named the way the grid named it — same label, same glyph, imported rather than
 * restated — because the operator is being asked to recognise a card they ticked.
 */
function SourceLine({ draft }: { draft: Draft }) {
  const { data: source, error } = useQuery(
    () => getSourceItem(draft.source_item_id!),
    [draft.source_item_id],
    { enabled: draft.source_item_id !== null },
  );

  // A topic run has no Source Item and never had one. Said out loud, because the
  // absence is the answer here — silence looks identical to the row not loading.
  if (draft.source_item_id === null) {
    return (
      <p className="text-xs text-muted-foreground">
        {draft.topic ? `Written from a topic — “${draft.topic}”` : "No source recorded."}
      </p>
    );
  }
  if (error !== null) {
    return (
      <p className="text-xs text-muted-foreground">
        Source #{draft.source_item_id} could not be read: {error}
      </p>
    );
  }
  if (source === null) return <Skeleton className="h-16" />;

  const Glyph = KIND_GLYPH[source.kind];
  return (
    <div className="space-y-1.5 rounded-md border bg-muted/40 p-3">
      <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
        <Glyph className="size-3.5 shrink-0" />
        {KIND_LABEL[source.kind]}
        <span>·</span>
        <span className="truncate font-medium text-foreground">
          {source.author ?? "Unknown"}
        </span>
        <span>·</span>
        {timeAgo(source.published_at)}
        {source.url ? (
          <a
            href={source.url}
            target="_blank"
            rel="noreferrer"
            className="ml-auto flex shrink-0 items-center gap-1 hover:text-foreground"
          >
            <ExternalLink className="size-3" />
            Open
          </a>
        ) : null}
      </p>
      {/* Two lines of the source's own text. Enough to recognise the card that
          was ticked; the rest of it is one click away, on the post itself. */}
      <p className="line-clamp-2 text-xs leading-relaxed">{source.text}</p>
    </div>
  );
}

/** The shape of the screen before the draft, its Page or its layout arrive. */
function DetailSkeleton() {
  return (
    <div className="grid gap-6 lg:grid-cols-[340px_minmax(0,1fr)]">
      <Skeleton className="aspect-896/1120 rounded-md" />
      <div className="space-y-4">
        <Skeleton className="h-8" />
        <Skeleton className="h-28" />
        <Skeleton className="h-40" />
      </div>
    </div>
  );
}

function Generating({ draft }: { draft: Draft }) {
  return (
    <div className="flex min-h-72 items-center justify-center rounded-lg border border-dashed p-10">
      <div className="w-full max-w-sm space-y-3">
        <div className="flex items-center justify-end text-sm">
          <span className="tabular-nums text-muted-foreground">{draft.progress_pct}%</span>
        </div>
        <div className="h-1 w-full overflow-hidden rounded-full bg-border">
          <div
            className="h-full bg-gold transition-[width] duration-500"
            style={{ width: `${draft.progress_pct}%` }}
          />
        </div>
        <p className="text-center text-sm">{draft.progress_step}</p>
        <p className="text-center text-xs text-muted-foreground">
          Leaving this screen does not cancel it.
        </p>
      </div>
    </div>
  );
}

function Field({
  label,
  hint,
  flagged,
  regenerate,
  children,
}: {
  label: string;
  hint?: string;
  flagged?: boolean;
  /** Ask the writer for this field again. Absent on fields it cannot rewrite. */
  regenerate?: React.ReactNode;
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
      {/* Its own row, between the label and the box it rewrites. It used to be a
          word inside the `<Label>`, which left nowhere for the prompt input to
          go — and an `<input>` inside a `<label>` steals the click that should
          focus the field. */}
      {regenerate}
      {children}
    </div>
  );
}

/** Ratios are fractions of the card, and the server clamps to the same range. */
function clamp01(value: number): number {
  return Math.min(1, Math.max(0, value));
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
    highlight_phrases: [...draft.highlight_phrases],
    image_prompt: draft.image_prompt ?? "",
    inset_size_px: draft.inset_size_px,
    inset_x_ratio: draft.inset_x_ratio,
    inset_y_ratio: draft.inset_y_ratio,
    inset_border_width_px: draft.inset_border_width_px,
    inset_border_color: draft.inset_border_color,
    template: draft.template,
  };
}
