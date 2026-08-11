"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2, Sparkles } from "lucide-react";
import { toast } from "sonner";

import { ScreenHeader } from "@/components/screen";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { generate } from "@/lib/api/drafts";
import { usePageScope } from "@/lib/page-scope";

/**
 * Write a post from a topic, with no Source Item behind it.
 *
 * This was the strip in the Sources dock, and it moved back here at the
 * client's request — "it looks like the Manual page no longer exists, could we
 * move this section back". It is a *move*, not a copy: the dock no longer
 * offers a topic box, so there is one place to type one.
 *
 * The dock was not a bad home for it. It was folded in there when the separate
 * `/generate` screen was deleted, and the reasoning holds — the topic applies
 * only while the Cart is empty, which is exactly when the dock has room. What
 * it could not be was a *destination*, and the client has plans for one ("I
 * have some future plans for the Manual page, but for now I don't need anything
 * beyond this"). A strip inside another screen's footer has nowhere to grow.
 *
 * Deliberately thin for now. Everything here is one thing — a topic, and the
 * button that spends money on it — because building the room before there is
 * anything to put in it is how a screen ends up with a layout nobody wants.
 */
export default function ManualScreen() {
  const router = useRouter();
  const { page } = usePageScope();
  const [topic, setTopic] = useState("");
  const [running, setRunning] = useState(false);

  const ready = topic.trim().length > 0 && page !== null;

  async function run() {
    if (!page || !ready) return;
    setRunning(true);
    try {
      // No sources, by definition. `start_run` treats a topic run as one draft
      // per Page, and nothing binds the story except the words below.
      const ids = await generate({ sources: [], page_ids: [page.id], topic: topic.trim() });
      setTopic("");
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
    <div className="w-full pb-16 lg:min-h-0 lg:flex-1 lg:overflow-y-auto lg:pr-3">
      <ScreenHeader
        title="Manual"
        hint="Write a post from a topic, with no source behind it."
      />

      {/* Bounded rather than full width. This is a single field, and a textarea
          running the width of a 1600px shell reads as a document editor. */}
      <div className="max-w-2xl space-y-4">
        <div className="space-y-2">
          <label htmlFor="topic" className="text-sm font-medium">
            Topic
          </label>
          {/* A textarea, not the dock's single-line input. The box is the whole
              brief here, and a topic worth writing out — a person, a year, the
              angle to take — does not fit on one line. */}
          <Textarea
            id="topic"
            value={topic}
            rows={4}
            onChange={(event) => setTopic(event.target.value)}
            placeholder="The Great Molasses Flood, Boston 1919"
            className="text-sm"
          />
          <p className="text-xs leading-relaxed text-muted-foreground">
            A topic-only Draft has no Source Item — nothing binds the story
            except the topic itself, so the writer is working from what the model
            already knows rather than from an article. Everything else is the
            same run: the same prompts, the same brand rules, the same card.
          </p>
        </div>

        <div className="flex items-center gap-3">
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
          {/* Said next to the button that does it, not in a tooltip: this is
              the click that pays for an image. */}
          <p className="text-xs text-muted-foreground">
            {page ? `For ${page.name}. ` : ""}Generating buys one image.
          </p>
        </div>
      </div>
    </div>
  );
}
