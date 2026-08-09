import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

import { cookies } from "next/headers";

import { Sidebar } from "@/components/sidebar";
import { COLLAPSE_COOKIE } from "@/lib/sidebar-cookie";
import { CartProvider } from "@/lib/cart";
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
  const collapsed = (await cookies()).get(COLLAPSE_COOKIE)?.value !== "0";

  return (
    <html
      lang="en"
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
        {/* The Cart sits above the router so it survives Sources → Generate. */}
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
      </body>
    </html>
  );
}
