"use client";

import { useRef, useState } from "react";
import { Eraser, Highlighter } from "lucide-react";

import { splitOnHighlights } from "@/components/composed-image";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/**
 * The hook, with its gold shown where it will actually fall.
 *
 * Highlighting used to be a list of chips you typed phrases into, which asked
 * the operator to retype text that was already on screen and to get it exactly
 * right — a phrase off by one character renders nothing. Here you select the
 * words and press a button.
 *
 * The trick is the old repo's and it is worth keeping: a transparent textarea
 * sits on top of a div that mirrors its text and colours it. Same box metrics
 * on both, so the caret and the colour stay aligned. Colour only, never weight
 * — bold would change the glyph widths and the two layers would drift apart.
 */

const BOX =
  "w-full rounded-md border px-3 py-2 text-sm leading-relaxed whitespace-pre-wrap break-words";

function has(phrases: string[], phrase: string) {
  return phrases.some((candidate) => candidate.toLowerCase() === phrase.toLowerCase());
}

export function HookField({
  value,
  phrases,
  rows = 5,
  onChange,
  onPhrasesChange,
}: {
  value: string;
  phrases: string[];
  /** Five fits a hook in the drawer. The layout editor's sample runs longer,
      and the box does not scroll — text past the last row is simply not there. */
  rows?: number;
  onChange: (value: string) => void;
  onPhrasesChange: (phrases: string[]) => void;
}) {
  const textarea = useRef<HTMLTextAreaElement>(null);
  const backdrop = useRef<HTMLDivElement>(null);
  const [selection, setSelection] = useState("");

  const segments = value ? splitOnHighlights(value, phrases) : [];
  /** Phrases the model returned that are not in the hook, so render no gold. */
  const absent = phrases.filter((phrase) => phrase && !value.includes(phrase));

  function readSelection() {
    const box = textarea.current;
    if (!box || box.selectionStart === box.selectionEnd) return setSelection("");
    setSelection(box.value.slice(box.selectionStart, box.selectionEnd).trim());
  }

  function toggle() {
    if (!selection) return;
    onPhrasesChange(
      has(phrases, selection)
        ? phrases.filter((p) => p.toLowerCase() !== selection.toLowerCase())
        : [...phrases, selection],
    );
  }

  return (
    <div className="space-y-2">
      <div className="relative">
        <div
          ref={backdrop}
          aria-hidden
          className={cn(BOX, "pointer-events-none absolute inset-0 overflow-hidden border-transparent")}
        >
          {segments.map((segment, index) => (
            <span key={index} className={segment.highlight ? "text-gold" : undefined}>
              {segment.text}
            </span>
          ))}
          {/* A trailing newline needs a glyph, or the backdrop is shorter than
              the textarea and the last line sits a row off. */}
          {value.endsWith("\n") ? "​" : null}
        </div>
        <textarea
          ref={textarea}
          rows={rows}
          className={cn(BOX, "relative resize-none bg-transparent")}
          style={{ color: "transparent", caretColor: "var(--foreground)" }}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          onSelect={readSelection}
          onScroll={() => {
            if (backdrop.current && textarea.current) {
              backdrop.current.scrollTop = textarea.current.scrollTop;
            }
          }}
        />
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <Button type="button" variant="outline" size="sm" disabled={!selection} onClick={toggle}>
          <Highlighter className="size-3.5" />
          {selection && has(phrases, selection) ? "Remove highlight" : "Highlight selection"}
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="text-muted-foreground"
          disabled={phrases.length === 0}
          onClick={() => onPhrasesChange([])}
        >
          <Eraser className="size-3.5" />
          Clear
        </Button>
        <span className="ml-auto text-[11px] text-muted-foreground">
          {phrases.length} highlighted · 5–8 expected
        </span>
      </div>

      {absent.length > 0 ? (
        /* Only the model can produce these — you cannot select text that is not
           there. Worth saying, because they are invisible: a phrase that does
           not appear simply renders nothing. */
        <p className="text-[11px] text-muted-foreground">
          {absent.length} phrase(s) are not in the hook and render nothing:{" "}
          <span className="line-through">{absent.slice(0, 3).join(", ")}</span>
        </p>
      ) : null}
    </div>
  );
}
