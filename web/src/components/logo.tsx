/**
 * The mark is the Composed Image itself — a 4:5 card, the hero above, the text
 * panel below the divider, and the gold Highlight Phrase inside it.
 *
 * Drawn as an outline, not the solid card `web/design/icon.svg` uses. The rail sits
 * it next to lucide icons, and a filled 20px card beside 1.5px strokes reads as
 * a blob rather than a sibling — so this is lucide's own geometry: a 24 viewBox
 * at stroke-width 2, which lands at the same optical weight as the nav icons at
 * any size they share. The favicon stays solid; a tab strip has no stroked
 * icons to match, and mass is what survives 16px there.
 *
 * The card takes `currentColor` so it inverts with the theme; the gold is
 * pinned to `--gold`, the same value the rendered post is stamped with.
 *
 * The source of truth is `web/design/mark.svg`. Kept inline rather than an <img> so
 * `currentColor` resolves — a linked SVG renders in its own document and never
 * sees the theme.
 */
export function Logo({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      // 1.6, not lucide's 2. The mark renders at `size-5` beside `size-4`
      // icons, so an identical stroke-width would come out 1.67px against
      // their 1.33px — 2 × 16/20 is what actually matches on screen.
      strokeWidth={1.6}
      strokeLinecap="round"
      strokeLinejoin="round"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      aria-hidden="true"
    >
      {/* the card */}
      <rect x="5" y="3" width="14" height="18" rx="2.5" />
      {/* hero above, text panel below */}
      <path d="M5 14h14" />
      {/* Highlight Phrase — the one filled element, so the accent reads as a
          mark on the panel rather than another line of the drawing. */}
      <path d="M8.4 17.6h4.2" stroke="var(--gold)" strokeWidth={1.9} />
    </svg>
  );
}
