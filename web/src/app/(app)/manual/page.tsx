"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ImageIcon, Loader2, Sparkles, X } from "lucide-react";
import { toast } from "sonner";

import { ComposedImage } from "@/components/composed-image";
import { ScreenHeader } from "@/components/screen";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { createManualDraft, generate } from "@/lib/api/drafts";
import { getPageLayout } from "@/lib/api/layout";
import { usePageScope } from "@/lib/page-scope";
import { useQuery } from "@/lib/use-query";

/**
 * The two ways to start a post with no Source Item behind it.
 *
 * **Tabs, not two columns**, and that is the old app's shape as well
 * (`generate-panel.tsx:343`, `GenerateMode = "ai" | "manual"`). They are
 * alternatives rather than steps: one costs nothing and the other buys an
 * image, and nobody is doing both at once. Side by side they competed for the
 * width that the hand-written form actually needs for its live card.
 *
 * **Write it yourself** is the old app's manual mode, restored at the client's
 * request — "Create a draft for {page} without calling Gemini". Hook, caption,
 * first comment, and an optional picture that becomes the hero.
 *
 * **From a topic** is the strip that used to sit in the Sources dock. It does
 * call the writer; the difference from a source run is only that nothing binds
 * the story except the words typed here.
 */
export default function ManualScreen() {
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <ScreenHeader
        title="Manual"
        hint="Start a post with no source behind it — write it yourself, or from a topic."
      />

      <Tabs defaultValue="write" className="flex min-h-0 flex-1 flex-col gap-6">
        {/* Same trigger sizing as the Sources tabs, so the two screens read as
            the same control rather than two takes on it. */}
        <TabsList className="shrink-0 gap-1.5 p-1 *:min-w-36 *:px-4">
          <TabsTrigger value="write">Write it yourself</TabsTrigger>
          <TabsTrigger value="topic">From a topic</TabsTrigger>
        </TabsList>

        <TabsContent value="write" className="min-h-0 flex-1 overflow-y-auto pr-3">
          <WriteItYourself />
        </TabsContent>
        <TabsContent value="topic" className="min-h-0 flex-1 overflow-y-auto pr-3">
          <FromATopic />
        </TabsContent>
      </Tabs>
    </div>
  );
}

/**
 * The old app's manual draft: every field typed, nothing generated.
 *
 * Laid out like the review drawer — card on the left, copy on the right — for
 * the reason the drawer has it that way: the hook is *drawn on the picture*, so
 * typing it without seeing where it lands is guesswork. The old app had no
 * preview here and its manual drafts were the ones that came out wrong.
 */
function WriteItYourself() {
  const router = useRouter();
  const { page, pageId } = usePageScope();
  const [hook, setHook] = useState("");
  const [caption, setCaption] = useState("");
  const [firstComment, setFirstComment] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const picker = useRef<HTMLInputElement>(null);

  const { data: layoutResult } = useQuery(() => getPageLayout(pageId!), [pageId], {
    enabled: pageId !== null,
  });
  const layout = layoutResult?.layout ?? null;

  // Any one of the three is enough, matching the server. A picture alone is not
  // a post, and the server refuses that case rather than storing an image with
  // nothing to say.
  const ready = Boolean(hook.trim() || caption.trim() || firstComment.trim());

  // The object URL outlives the render that made it, so it is revoked on
  // replace and on unmount — otherwise every re-pick leaks one for the life of
  // the page.
  useEffect(() => {
    return () => {
      if (preview) URL.revokeObjectURL(preview);
    };
  }, [preview]);

  function choose(chosen: File | null) {
    setFile(chosen);
    setPreview(chosen ? URL.createObjectURL(chosen) : null);
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!page || !ready) return;
    setSaving(true);
    try {
      const draft = await createManualDraft({
        page_id: page.id,
        hook,
        caption,
        first_comment: firstComment,
        file,
      });
      toast.success("Draft created.", {
        description: file
          ? "The card was drawn around your picture."
          : "No picture yet, so there is no card to publish.",
      });
      // Straight to the draft rather than the queue: this one was written by
      // hand, so the thing worth seeing is how it came out on the card.
      router.push(`/review/${draft.id}`);
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "Could not create that draft");
    } finally {
      setSaving(false);
    }
  }

  return (
    // Bounded rather than let loose across the shell's 1600px. These are three
    // textareas, and a text field the width of the screen reads as a document
    // editor — the same reason the topic tab is capped.
    <form
      onSubmit={submit}
      className="grid max-w-5xl gap-8 lg:grid-cols-[340px_minmax(0,1fr)]"
    >
      {/* Sticky, like the drawer's: the card has to stay in view while the copy
          beside it scrolls, or the preview is not a preview. */}
      <div className="space-y-3 lg:sticky lg:top-0 lg:self-start">
        {layout && page ? (
          <ComposedImage
            layout={layout}
            page={page}
            overlayText={hook}
            highlightPhrases={[]}
            heroSrc={preview}
          />
        ) : (
          <Skeleton className="aspect-896/1120 rounded-md" />
        )}

        <input
          ref={picker}
          id="manual-image"
          type="file"
          accept="image/*"
          className="hidden"
          onChange={(event) => {
            choose(event.target.files?.[0] ?? null);
            // Cleared, so picking the same file twice fires again.
            event.target.value = "";
          }}
        />
        <div className="flex gap-1">
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="flex-1"
            onClick={() => picker.current?.click()}
          >
            <ImageIcon className="size-3.5" />
            {file ? "Replace image" : "Choose image"}
          </Button>
          {file ? (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="text-muted-foreground"
              onClick={() => choose(null)}
            >
              <X className="size-3.5" />
              Remove
            </Button>
          ) : null}
        </div>
        <p className="text-[11px] leading-relaxed text-muted-foreground">
          {file
            ? "Your picture is the hero. The panel, the hook and the watermark are drawn over it."
            : "Optional. Without one there is no card to publish yet — the gradient above is a placeholder, not the post."}
        </p>
      </div>

      <div className="min-w-0 space-y-6">
        <p className="text-xs text-muted-foreground">
          Nothing on this tab calls a model.
        </p>

        <div className="space-y-2">
          <Label htmlFor="manual-hook">Image text overlay</Label>
          <Textarea
            id="manual-hook"
            value={hook}
            rows={3}
            onChange={(event) => setHook(event.target.value)}
            placeholder="Scroll-stopping opening line…"
            className="text-sm"
          />
          {/* The rule the writer is held to, stated rather than enforced — a
              person typing here has decided, and the server records it as a
              warning instead of refusing the draft. */}
          <p className="text-[11px] text-muted-foreground">
            Drawn on the panel. Under 65 words and no questions, by the brand
            rules — broken here, it is recorded as a warning rather than refused.
          </p>
        </div>

        <div className="space-y-2">
          <Label htmlFor="manual-caption">Caption</Label>
          <Textarea
            id="manual-caption"
            value={caption}
            rows={5}
            onChange={(event) => setCaption(event.target.value)}
            placeholder="Recap / post caption…"
            className="text-sm"
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="manual-first-comment">First comment</Label>
          <Textarea
            id="manual-first-comment"
            value={firstComment}
            rows={10}
            onChange={(event) => setFirstComment(event.target.value)}
            placeholder="Main body / CTA as first comment…"
            className="text-sm leading-relaxed"
          />
        </div>

        <div className="flex items-center gap-3 border-t pt-4">
          <Button type="submit" disabled={!ready || saving || !page}>
            {saving ? <Loader2 className="size-4 animate-spin" /> : null}
            Create draft
          </Button>
          {!ready ? (
            <p className="text-xs text-muted-foreground">
              Needs a hook, a caption or a first comment.
            </p>
          ) : null}
        </div>
      </div>
    </form>
  );
}

/** The strip that used to live in the Sources dock. This one does call the writer. */
function FromATopic() {
  const router = useRouter();
  const { page } = usePageScope();
  const [topic, setTopic] = useState("");
  const [noImage, setNoImage] = useState(false);
  const [running, setRunning] = useState(false);

  const ready = topic.trim().length > 0 && page !== null;

  async function run() {
    if (!page || !ready) return;
    setRunning(true);
    try {
      const ids = await generate({
        sources: [],
        page_ids: [page.id],
        topic: topic.trim(),
        no_image: noImage,
      });
      setTopic("");
      setNoImage(false);
      toast.success(`${ids.length} draft${ids.length === 1 ? "" : "s"} generating.`, {
        description: "Progress is on the Review screen.",
      });
      router.push("/review");
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "Generate failed");
    } finally {
      setRunning(false);
    }
  }

  return (
    // Bounded: one field, and a textarea running the width of a 1600px shell
    // reads as a document editor.
    <div className="max-w-2xl space-y-4">
      <div className="space-y-2">
        <Label htmlFor="topic">Topic</Label>
        <Textarea
          id="topic"
          value={topic}
          rows={4}
          onChange={(event) => setTopic(event.target.value)}
          placeholder="The Great Molasses Flood, Boston 1919"
          className="text-sm"
        />
        <p className="text-xs leading-relaxed text-muted-foreground">
          The writer produces the whole post and buys a hero for it. Nothing binds
          the story except the topic itself, so it works from what the model
          already knows rather than from an article — otherwise it is the same
          run as any other: the same prompts, the same brand rules, the same card.
        </p>
      </div>

      {/* The picture is the only part of a topic run that costs money, so the
          option to skip it belongs beside the button that spends it. */}
      <label className="flex w-fit cursor-pointer items-center gap-2 text-xs text-muted-foreground">
        <input
          type="checkbox"
          checked={noImage}
          onChange={(event) => setNoImage(event.target.checked)}
          className="size-3.5 cursor-pointer accent-primary"
        />
        No image — text only, and nothing to pay for
      </label>

      <Button
        className="bg-gold text-gold-foreground hover:bg-gold/90"
        disabled={!ready || running}
        onClick={run}
      >
        {running ? (
          <Loader2 className="size-4 animate-spin" />
        ) : (
          <Sparkles className="size-4" />
        )}
        Generate 1 draft
      </Button>
    </div>
  );
}
