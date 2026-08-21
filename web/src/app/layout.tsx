import type { Metadata } from "next";
import { Geist, JetBrains_Mono } from "next/font/google";
import "./globals.css";

import { ThemeProvider } from "next-themes";

import { Toaster } from "@/components/ui/sonner";

// `--font-sans` is the name globals.css maps `--font-sans` onto; naming it
// `--font-geist-sans` here leaves that mapping pointing at nothing.
const geistSans = Geist({ variable: "--font-sans", subsets: ["latin"] });

// JetBrains Mono for the data voice: the 11px uppercase section labels, table
// columns, ids, metrics and `tabular-nums` values — the same face polylane.com
// sets data and code in. Every place that says `font-mono` or `tabular-nums`
// picks this up; the UI roman stays Geist.
const jetbrainsMono = JetBrains_Mono({
  variable: "--font-jetbrains-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "fb-agent",
  description: "Draft factory for History Retraced.",
};

/**
 * Document, fonts, theme, toasts — everything both the app and the login
 * screen need. The rail, the Page scope and the Cart moved down into
 * `(app)/layout.tsx`, because `/login` has none of them.
 */
export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html
      lang="en"
      // next-themes writes `class="dark"` and `style="color-scheme"` onto this
      // element from a blocking script, before React hydrates — which is
      // precisely the mismatch React would otherwise shout about. Scoped to
      // this element only; it does not silence anything below it.
      suppressHydrationWarning
      className={`${geistSans.variable} ${jetbrainsMono.variable} h-full antialiased`}
    >
      {/*
        Desktop is a fixed viewport: the page itself never scrolls, and each
        screen scrolls its own panes instead — the queue, the source grid and
        the Cart all stay put while their contents move. Below `lg` that
        inverts, because two independent scroll areas side by side do not fit
        on a phone.
      */}
      <body className="flex min-h-full flex-col lg:h-screen lg:flex-row lg:overflow-hidden">
        {/*
          The Toaster reads the theme too (`ui/sonner.tsx` has called
          `useTheme` since it was generated, and until now got nothing back and
          fell through to its "system" default).

          The theme is *not* read from a cookie the way the rail's width is.
          That trick exists because the sidebar renders its own width on the
          server; next-themes solves the same first-paint problem differently,
          with a blocking inline script that sets the class before anything is
          painted — so there is no flash to fix and no second source of truth.
          `system` is the default, so an operator who never touches the control
          follows the OS.
        */}
        <ThemeProvider
          attribute="class"
          defaultTheme="system"
          enableSystem
          // The shell animates width and colour on a 300ms transition. Without
          // this, flipping the theme drags every one of those through the
          // colour change and the whole screen smears.
          disableTransitionOnChange
        >
          {children}
          <Toaster position="bottom-right" />
        </ThemeProvider>
      </body>
    </html>
  );
}
