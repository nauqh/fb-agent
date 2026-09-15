"use client";

import { ThemeProvider as NextThemesProvider } from "next-themes";
import type { ComponentProps } from "react";

/**
 * next-themes renders its no-flash `<script>` from inside the component, and
 * React 19 logs "Encountered a script tag while rendering React component"
 * whenever it creates one on the client (it is never executed there anyway).
 * The script only has to run once, from the server HTML, before paint. So the
 * server keeps it executable and the client renders it as a data block
 * (`application/json`), which React exempts from the warning. The `type`
 * mismatch is silent: next-themes sets `suppressHydrationWarning` on the tag.
 * This has to be a client component - in `layout.tsx` the `typeof window`
 * check would only ever see the server.
 */
export function ThemeProvider(props: ComponentProps<typeof NextThemesProvider>) {
  return (
    <NextThemesProvider
      scriptProps={typeof window === "undefined" ? undefined : { type: "application/json" }}
      {...props}
    />
  );
}
