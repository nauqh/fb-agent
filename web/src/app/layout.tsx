import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

import { cookies } from "next/headers";
import { ThemeProvider } from "next-themes";

import { Sidebar } from "@/components/sidebar";
import { COLLAPSE_COOKIE } from "@/lib/sidebar-cookie";
import { PAGE_COOKIE, parsePageCookie } from "@/lib/page-cookie";
import { CartProvider } from "@/lib/cart";
import { PageScopeProvider } from "@/lib/page-scope";
import { Toaster } from "@/components/ui/sonner";

// `--font-sans` is the name globals.css maps `--font-sans` onto; naming it
// `--font-geist-sans` here leaves that mapping pointing at nothing.
const geistSans = Geist({ variable: "--font-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "fb-agent",
  description: "Draft factory for History Retraced.",
};

export default async function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  // Read here rather than in the Sidebar so the very first paint is already the
  // right width. `cookies()` makes this layout dynamic, which costs nothing:
  // every screen under it is a client component fed by the API anyway.
  //
  // Collapsed is the default, so the test is `!== "0"` rather than `=== "1"`:
  // absent cookie means a rail that has never been touched, and that starts
  // narrow. Only an explicit "0" — someone having opened it — keeps it wide.
  const jar = await cookies();
  const collapsed = jar.get(COLLAPSE_COOKIE)?.value !== "0";

  // Null when absent, which the provider resolves to the first Page. It is not
  // defaulted to 1 here: ids come from the database, and the project reseeds it
  // by convention.
  const pageId = parsePageCookie(jar.get(PAGE_COOKIE)?.value);

  return (
    <html
      lang="en"
      // next-themes writes `class="dark"` and `style="color-scheme"` onto this
      // element from a blocking script, before React hydrates — which is
      // precisely the mismatch React would otherwise shout about. Scoped to
      // this element only; it does not silence anything below it.
      suppressHydrationWarning
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
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
          Outermost of the three, because the Toaster reads the theme too
          (`ui/sonner.tsx` has called `useTheme` since it was generated, and
          until now got nothing back and fell through to its "system" default).

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
          {/* The Cart sits above the router so it survives Sources → Generate.
              Page scope wraps it, because the Cart's Generate button reads the
              selected Page to decide what it is generating for. */}
          <PageScopeProvider defaultPageId={pageId}>
            <CartProvider>
              <Sidebar defaultCollapsed={collapsed} />
              {/* `min-w-0`: without it this flex child takes its width from its
                  content, and a wide table inside a screen pushes the rail off the
                  left edge instead of scrolling in its own pane. */}
              <main className="mx-auto flex w-full max-w-[1600px] flex-1 flex-col px-6 py-6 lg:min-h-0 lg:min-w-0 lg:overflow-hidden">
                {children}
              </main>
              <Toaster position="bottom-right" />
            </CartProvider>
          </PageScopeProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
