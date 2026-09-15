"use client";

import { useEffect, useId, useState } from "react";
import { useTheme } from "next-themes";
import mermaid from "mermaid";

// Fumadocs ships only the remark plugin that turns ```mermaid blocks into this
// component; the component itself is ours, as their docs recommend. Finished
// SVGs are kept per theme and source, because moving between docs remounts every
// diagram: without this each visit re-rendered from scratch, and showing the
// raw source while it did so flashed the diagram's text on every page switch.
const rendered = new Map<string, string>();

export function Mermaid({ chart }: { chart: string }) {
  const id = useId().replace(/[^a-zA-Z0-9_-]/g, "");
  const { resolvedTheme } = useTheme();
  const key = `${resolvedTheme}:${chart}`;
  const [result, setResult] = useState<{ key: string; svg?: string; failed?: boolean }>({
    key: "",
  });
  const svg = rendered.get(key) ?? (result.key === key ? result.svg : undefined);

  useEffect(() => {
    if (rendered.has(key)) return;
    let cancelled = false;

    mermaid.initialize({
      startOnLoad: false,
      securityLevel: "strict",
      fontFamily: "inherit",
      theme: resolvedTheme === "dark" ? "dark" : "default",
    });

    mermaid
      .render(`mermaid-${id}`, chart)
      .then(({ svg: output }) => {
        rendered.set(key, output);
        if (!cancelled) setResult({ key, svg: output });
      })
      .catch(() => {
        if (!cancelled) setResult({ key, failed: true });
      });

    return () => {
      cancelled = true;
    };
  }, [chart, id, key, resolvedTheme]);

  // The source is shown only for a diagram that will not parse, never while one
  // is still drawing.
  if (result.key === key && result.failed) {
    return (
      <pre className="overflow-x-auto rounded-lg border p-4" data-mermaid-fallback>
        {chart}
      </pre>
    );
  }
  if (!svg) return null;

  return (
    <div
      className="my-6 flex justify-center overflow-x-auto rounded-lg border p-4"
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  );
}
