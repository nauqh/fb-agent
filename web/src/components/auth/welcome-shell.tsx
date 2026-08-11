import { CalendarClock, PenLine, Images } from "lucide-react";
import type { ReactNode } from "react";

import { Logo } from "@/components/logo";

/**
 * The signed-out frame: what this is on the left, the form on the right.
 *
 * The old app's shape (`components/auth/welcome-shell.tsx`), with its copy
 * replaced rather than reworded. Its three points sold a product to strangers —
 * "For creators and teams", "Automate your content pipeline". This screen has
 * exactly one visitor, who owns the thing, so the panel says what the app does
 * instead of why it is worth having.
 *
 * The violet is gone with it. This app has one accent, `--gold`, and it is the
 * colour stamped onto every published card.
 */
const what = [
  {
    icon: PenLine,
    title: "Drafts, written and reviewed",
    description: "A hook, a caption and a first comment per source item.",
  },
  {
    icon: Images,
    title: "Cards, composed",
    description: "The hero and the text panel, rendered as one 4:5 image.",
  },
  {
    icon: CalendarClock,
    title: "Published through Metricool",
    description: "Its planner holds the schedule. Nothing is mirrored here.",
  },
] as const;

export function WelcomeShell({ children }: { children: ReactNode }) {
  return (
    <div className="grid min-h-svh w-full lg:grid-cols-2">
      <section className="relative flex min-h-[34vh] flex-col overflow-hidden bg-zinc-950 px-8 py-8 text-zinc-50 sm:px-12 lg:min-h-svh lg:px-14 lg:py-10">
        {/* Two washes rather than one, so the panel has a light source. Both
            are gold at low alpha — the same hue as the mark, not a second
            accent introduced for a background. */}
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_80%_60%_at_20%_0%,var(--gold),transparent_55%)] opacity-[0.14]"
        />
        <div
          aria-hidden
          className="pointer-events-none absolute -right-24 top-1/3 size-72 rounded-full bg-[var(--gold)] opacity-[0.06] blur-3xl"
        />

        <header className="relative z-10 shrink-0">
          <div className="flex items-center gap-2.5">
            <span className="flex size-9 items-center justify-center rounded-xl bg-white/10 ring-1 ring-white/15">
              <Logo className="size-5" />
            </span>
            <span className="text-sm font-semibold tracking-tight">fb-agent</span>
          </div>
        </header>

        <div className="relative z-10 flex flex-1 flex-col justify-center py-8 lg:py-12">
          <div className="max-w-lg">
            <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl lg:text-[2.75rem] lg:leading-[1.15]">
              The draft factory
            </h1>
            <p className="mt-4 text-base leading-relaxed text-zinc-400 sm:text-lg">
              Sources in, finished posts out — reviewed by hand before anything
              reaches a page.
            </p>

            <ul className="mt-8 hidden space-y-5 sm:block lg:mt-10">
              {what.map(({ icon: Icon, title, description }) => (
                <li key={title} className="flex gap-4">
                  <span className="mt-0.5 flex size-10 shrink-0 items-center justify-center rounded-lg bg-white/10 ring-1 ring-white/10">
                    <Icon className="size-5 text-[var(--gold)]" />
                  </span>
                  <div>
                    <p className="font-medium text-zinc-100">{title}</p>
                    <p className="mt-0.5 text-sm leading-relaxed text-zinc-400">
                      {description}
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </section>

      <section className="flex items-center justify-center px-6 py-12 sm:px-10">
        <div className="w-full max-w-sm">{children}</div>
      </section>
    </div>
  );
}
