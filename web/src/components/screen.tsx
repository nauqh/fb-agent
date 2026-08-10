import { PageSwitcher } from "@/components/page-switcher";

/**
 * Every screen's title row — and the one place the Page switcher is mounted.
 *
 * The switcher lives here rather than in each screen so that adding a screen
 * cannot mean forgetting it. It renders nothing while there is a single Page,
 * so this costs the one-page layout no space.
 */
export function ScreenHeader({
  title,
  hint,
  action,
  switcher = true,
}: {
  title: string;
  hint?: React.ReactNode;
  action?: React.ReactNode;
  /**
   * Off for a screen that is mostly *not* per-Page.
   *
   * Global is the one: the competitor pool and the prompt files belong to the
   * account, and a Page name in the title row claimed the whole screen was
   * scoped to it. There the switcher moves down to the one card it governs.
   */
  switcher?: boolean;
}) {
  return (
    <div className="flex shrink-0 items-end justify-between gap-6 pb-5">
      <div className="space-y-1">
        <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
        {hint ? <p className="text-sm text-muted-foreground">{hint}</p> : null}
      </div>
      {/* The switcher sits inboard of the screen's own action, so the primary
          button stays at the right edge where it is on every screen. */}
      <div className="flex shrink-0 items-center gap-3">
        {switcher ? <PageSwitcher /> : null}
        {action}
      </div>
    </div>
  );
}

export function Empty({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-72 items-center justify-center rounded-lg border border-dashed p-10 text-center text-sm text-muted-foreground">
      {children}
    </div>
  );
}
