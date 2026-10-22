"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ImageIcon, Loader2, Sparkles, X } from "lucide-react";
import { toast } from "sonner";

import { ComposedImage } from "@/components/composed-image";
import { HookField } from "@/components/hook-field";
import { Field, Regenerate } from "@/components/rewrite-field";
import { ScreenHeader } from "@/components/screen";
import { Loading } from "@/components/loading";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import {
  createManualDraft,
  generate,
  publishMode,
  rewriteUnsaved,
  type RegeneratableField,
} from "@/lib/api/drafts";
import { getWeb } from "@/lib/api/sources";
import { getPageLayout } from "@/lib/api/layout";
import { InsetSourceSelect, type InsetSource } from "@/components/inset-source-select";
import { usePageScope } from "@/lib/page-scope";
import { chars, words } from "@/lib/format";
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
 * request - "Create a draft for {page} without calling Gemini". Hook, caption,
 * first comment, and an optional picture that becomes the hero. Each field has
 * the review drawer's Write/Rewrite box (client, 2026-10-21): the writer is
 * there if asked, and nothing it proposes is saved until Create draft.
 *
 * **From a topic** is the strip that used to sit in the Sources dock. It does
 * call the writer; the difference from a source run is only that nothing binds
 * the story except the words typed here.
 *
 * Both can make a **quote card** (client, 2026-10-22): the hook set as type on
 * a dark ground, with no picture to upload or buy. A post's form, not a Page's,
 * because a Page mixes formats.
 */
export default function ManualScreen() {
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <ScreenHeader
        title="No source"
        hint="Start a post with no source behind it - write it yourself, or from a topic."
      />

      <Tabs defaultValue="write" className="flex min-h-0 flex-1 flex-col gap-6">
        {/* Same trigger sizing as the Sources tabs, so the two screens read as
            the same control rather than two takes on it. */}
        <TabsList className="shrink-0 *:min-w-36 *:px-4">
          <TabsTrigger value="write">Write it yourself</TabsTrigger>
          <TabsTrigger value="topic">From a topic</TabsTrigger>
        </TabsList>

        <TabsContent value="write" className="min-h-0 flex-1 overflow-y-auto pr-3 lift-room">
          <WriteItYourself />
        </TabsContent>
        <TabsContent value="topic" className="min-h-0 flex-1 overflow-y-auto pr-3 lift-room">
          <FromATopic />
        </TabsContent>
      </Tabs>
    </div>
  );
}

/**
 * The old app's manual draft: every field typed, nothing generated.
 *
 * Laid out like the review drawer - card on the left, copy on the right - for
 * the reason the drawer has it that way: the hook is *drawn on the picture*, so
 * typing it without seeing where it lands is guesswork. The old app had no
 * preview here and its manual drafts were the ones that came out wrong.
 */
function WriteItYourself() {
  const router = useRouter();
  const { page, pageId } = usePageScope();
  const [hook, setHook] = useState("");
  const [phrases, setPhrases] = useState<string[]>([]);
  const [caption, setCaption] = useState("");
  const [firstComment, setFirstComment] = useState("");
  const [source, setSource] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [findInset, setFindInset] = useState(false);
  const [insetSource, setInsetSource] = useState<InsetSource | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [quote, setQuote] = useState(false);
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
  // replace and on unmount - otherwise every re-pick leaks one for the life of
  // the page.
  useEffect(() => {
    return () => {
      if (preview) URL.revokeObjectURL(preview);
    };
  }, [preview]);

  const text: Record<RegeneratableField, string> = {
    hook,
    caption,
    first_comment: firstComment,
  };

  async function rewrite(field: RegeneratableField, instruction?: string) {
    if (!page) return;
    const proposal = await rewriteUnsaved(page.id, field, {
      keeping: text,
      instruction,
      source: source.trim(),
      quote,
    });
    if (field === "hook") {
      setHook(proposal.text);
      setPhrases(proposal.highlight_phrases ?? []);
    } else if (field === "caption") setCaption(proposal.text);
    else setFirstComment(proposal.text);
  }

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
        highlight_phrases: phrases,
        find_inset: findInset && !quote,
        inset_source: insetSource ?? page.inset_source,
        file: quote ? null : file,
        template: quote ? "quote" : undefined,
      });
      toast.success("Draft created.", {
        description: quote
          ? "The quote card is drawn."
          : file
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
    // editor - the same reason the topic tab is capped.
    <form
      onSubmit={submit}
      className="grid max-w-5xl gap-8 lg:grid-cols-[340px_minmax(0,1fr)]"
    >
      {/* Sticky, like the drawer's: the card has to stay in view while the copy
          beside it scrolls, or the preview is not a preview. */}
      <div className="space-y-3 lg:sticky lg:top-0 lg:self-start">
        <Tabs value={quote ? "quote" : "card"} onValueChange={(next) => setQuote(next === "quote")}>
          <TabsList className="w-full *:flex-1">
            <TabsTrigger value="card">Card</TabsTrigger>
            <TabsTrigger value="quote">Quote</TabsTrigger>
          </TabsList>
        </Tabs>
        {layout && page ? (
          <ComposedImage
            layout={quote ? { ...layout, template: "quote" } : layout}
            page={page}
            overlayText={hook}
            highlightPhrases={phrases}
            heroSrc={preview}
          />
        ) : (
          <Loading className="aspect-896/1120 rounded-2xl border" />
        )}
        {quote ? (
          <p className="text-xs text-muted-foreground">
            No picture needed. Highlights are set in bold italic.
          </p>
        ) : (
          <>

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
        {file ? null : (
          <p className="text-xs text-muted-foreground">
            Optional. The gradient is only a placeholder.
          </p>
        )}
        {/* Beside the picture it adds to. Reads the text typed on the right,
            once the draft is created. */}
        <div className="flex flex-wrap items-center gap-2">
          <label className="flex w-fit cursor-pointer items-center gap-2 text-xs text-muted-foreground">
            <input
              type="checkbox"
              checked={findInset}
              onChange={(event) => setFindInset(event.target.checked)}
              className="size-3.5 cursor-pointer accent-primary"
            />
            Let AI pick an inset picture
          </label>
          {findInset && page ? (
            <InsetSourceSelect
              value={insetSource ?? page.inset_source}
              onChange={setInsetSource}
            />
          ) : null}
        </div>
          </>
        )}
      </div>

      <div className="min-w-0 space-y-6">
        {/* A writing aid only: the drafts made here carry no Source Item, so
            this is not stored. Without it the writer has nothing but the three
            boxes, and a 1,500-character first comment cannot come from a hook. */}
        <Field label="Source" hint="optional · not saved">
          <Textarea
            value={source}
            rows={4}
            onChange={(event) => setSource(event.target.value)}
            placeholder="Paste the article, or its link. Write and Rewrite work from it."
            className="text-sm"
          />
        </Field>

        <Field
          label={quote ? "Quote" : "Image text overlay"}
          regenerate={
            <Regenerate
              label="Overlay"
              empty={!hook.trim()}
              ask={(instruction) => rewrite("hook", instruction)}
            />
          }
          hint={
            quote
              ? "first line is the heading"
              : `${words(hook)} words · limit 65, no question`
          }
          flagged={words(hook) > 65 || hook.includes("?")}
        >
          <HookField
            value={hook}
            phrases={phrases}
            rows={3}
            onChange={setHook}
            onPhrasesChange={setPhrases}
          />
        </Field>

        <Field
          label="Caption"
          regenerate={
            <Regenerate
              label="Caption"
              empty={!caption.trim()}
              ask={(instruction) => rewrite("caption", instruction)}
            />
          }
          hint={`${caption.split("\n").filter(Boolean).length} recap lines · max 5`}
        >
          <Textarea
            value={caption}
            rows={5}
            onChange={(event) => setCaption(event.target.value)}
            placeholder="Recap / post caption…"
            className="text-sm"
          />
        </Field>

        <Field
          label="First comment"
          regenerate={
            <Regenerate
              label="First comment"
              empty={!firstComment.trim()}
              ask={(instruction) => rewrite("first_comment", instruction)}
            />
          }
          hint={`${chars(firstComment)} · 1,500-2,100`}
          // Not on an empty box: nobody has written it yet, which is not a mistake.
          flagged={firstComment.length > 0 && (firstComment.length < 1500 || firstComment.length > 2100)}
        >
          <Textarea
            value={firstComment}
            rows={10}
            onChange={(event) => setFirstComment(event.target.value)}
            placeholder="Main body / CTA as first comment…"
            className="text-sm leading-relaxed"
          />
        </Field>

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
  const [article, setArticle] = useState("");
  const [writeArticle, setWriteArticle] = useState(true);
  const { data: mode } = useQuery(() => publishMode(), []);
  const [noImage, setNoImage] = useState(false);
  const [quote, setQuote] = useState(false);
  const [findInset, setFindInset] = useState(false);
  const [insetSource, setInsetSource] = useState<InsetSource | null>(null);
  const [running, setRunning] = useState(false);

  const pasted = article.trim();
  const ready = (topic.trim().length > 0 || pasted.length > 0) && page !== null;
  const offerArticle = pasted.length > 0 && page?.id === mode?.article_page_id;

  async function run() {
    if (!page || !ready) return;
    setRunning(true);
    try {
      // A pasted article goes in as a web source, so the writer works from it
      // and not from the topic alone. A bare link is read the way the Sources
      // Web tab reads one.
      const link = /^https?:\/\/\S+$/.test(pasted);
      const ids = await generate({
        sources: link
          ? [await getWeb(pasted)]
          : pasted
          ? [
              {
                kind: "web",
                external_id: `pasted-${Date.now()}`,
                author: null,
                synced_for_page_id: null,
                competitor_page_id: null,
                text: pasted,
                body: pasted,
                url: null,
                image_url: null,
                published_at: null,
                reactions: null,
                comments: null,
                shares: null,
              },
            ]
          : [],
        page_ids: [page.id],
        topic: pasted ? undefined : topic.trim(),
        write_article: offerArticle && writeArticle,
        no_image: noImage && !quote,
        template: quote ? "quote" : undefined,
        find_inset: findInset && !noImage && !quote,
        inset_source: insetSource ?? page.inset_source,
      });
      setTopic("");
      setArticle("");
      setNoImage(false);
      setQuote(false);
      setFindInset(false);
      setInsetSource(null);
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
          already knows rather than from an article - otherwise it is the same
          run as any other: the same prompts, the same brand rules, the same card.
        </p>
      </div>

      <div className="space-y-2">
        <Label htmlFor="article">Article</Label>
        <Textarea
          id="article"
          value={article}
          rows={8}
          onChange={(event) => setArticle(event.target.value)}
          placeholder="Paste an article, or its link, to write the post from"
          className="text-sm"
        />
        <p className="text-xs leading-relaxed text-muted-foreground">
          Optional. When set, the post is written from this article instead of the topic.
        </p>
      </div>

      {offerArticle ? (
        <label className="flex w-fit cursor-pointer items-center gap-2 text-xs text-muted-foreground">
          <input
            type="checkbox"
            checked={writeArticle}
            onChange={(event) => setWriteArticle(event.target.checked)}
            className="size-3.5 cursor-pointer accent-primary"
          />
          Write the website article too
        </label>
      ) : null}

      <label className="flex w-fit cursor-pointer items-center gap-2 text-xs text-muted-foreground">
        <input
          type="checkbox"
          checked={quote}
          onChange={(event) => setQuote(event.target.checked)}
          className="size-3.5 cursor-pointer accent-primary"
        />
        Quote card, no picture
      </label>

      {/* The picture is the only part of a topic run that costs money, so the
          option to skip it belongs beside the button that spends it. */}
      {!quote ? (
        <label className="flex w-fit cursor-pointer items-center gap-2 text-xs text-muted-foreground">
          <input
            type="checkbox"
            checked={noImage}
            onChange={(event) => setNoImage(event.target.checked)}
            className="size-3.5 cursor-pointer accent-primary"
          />
          Text only, no image
        </label>
      ) : null}

      {!noImage && !quote ? (
        <div className="flex flex-wrap items-center gap-2">
          <label className="flex w-fit cursor-pointer items-center gap-2 text-xs text-muted-foreground">
            <input
              type="checkbox"
              checked={findInset}
              onChange={(event) => setFindInset(event.target.checked)}
              className="size-3.5 cursor-pointer accent-primary"
            />
            Let AI pick an inset picture
          </label>
          {findInset && page ? (
            <InsetSourceSelect
              value={insetSource ?? page.inset_source}
              onChange={setInsetSource}
            />
          ) : null}
        </div>
      ) : null}

      <Button
        variant="gold"
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
