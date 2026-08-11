import { cookies } from "next/headers";

import { Sidebar } from "@/components/sidebar";
import { COLLAPSE_COOKIE } from "@/lib/sidebar-cookie";
import { PAGE_COOKIE, parsePageCookie } from "@/lib/page-cookie";
import { CartProvider } from "@/lib/cart";
import { PageScopeProvider } from "@/lib/page-scope";

/**
 * The signed-in app: rail, Page scope, Cart.
 *
 * A route group rather than a path segment, so every URL is exactly what it was
 * — `/review/12` is still `/review/12`. It exists because `/login` cannot have
 * a sidebar, and the sidebar used to live in the root layout, which wraps
 * everything including the login screen.
 */
export default async function AppLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
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
    /* The Cart sits above the router so it survives Sources → Generate. Page
       scope wraps it, because the Cart's Generate button reads the selected
       Page to decide what it is generating for. */
    <PageScopeProvider defaultPageId={pageId}>
      <CartProvider>
        <Sidebar defaultCollapsed={collapsed} />
        {/* `min-w-0`: without it this flex child takes its width from its
            content, and a wide table inside a screen pushes the rail off the
            left edge instead of scrolling in its own pane. */}
        <main className="mx-auto flex w-full max-w-[1600px] flex-1 flex-col px-6 py-6 lg:min-h-0 lg:min-w-0 lg:overflow-hidden">
          {children}
        </main>
      </CartProvider>
    </PageScopeProvider>
  );
}
