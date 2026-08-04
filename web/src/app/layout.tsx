import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

import { Nav } from "@/components/nav";
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

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
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
      <body className="flex min-h-full flex-col lg:h-screen lg:overflow-hidden">
        {/* The Cart sits above the router so it survives Sources → Generate. */}
        <CartProvider>
          <Nav />
          <main className="mx-auto flex w-full max-w-[1600px] flex-1 flex-col px-6 py-6 lg:min-h-0 lg:overflow-hidden">
            {children}
          </main>
          <Toaster position="bottom-right" />
        </CartProvider>
      </body>
    </html>
  );
}
