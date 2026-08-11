import { NextResponse, type NextRequest } from "next/server";

import { SESSION_COOKIE, isValidSession } from "@/lib/auth";

/**
 * Two jobs: keep strangers out, and add the API key to what gets through.
 *
 * `proxy.ts`, not `middleware.ts`: Next 16 renamed the file convention, and a
 * `middleware.ts` is not picked up — it fails silently, as an app that serves
 * fine while every API call comes back 401.
 *
 * The key half is the one the browser must never see. `lib/api/client.ts`
 * fetches the relative path `/api/...`, `next.config.ts` rewrites that to
 * FastAPI, and the key is attached here on the way through. So the secret lives
 * in this server's environment and is never in a bundle, a network tab, or a
 * page's HTML.
 *
 * Hence `API_KEY` and not `NEXT_PUBLIC_API_KEY`. The `NEXT_PUBLIC_` prefix
 * inlines a value into the client bundle at build time, which would publish the
 * key to every visitor and undo the whole arrangement.
 *
 * A missing `API_KEY` sends an empty header rather than throwing. The API
 * refuses an empty key, so the failure is 401s on every call — noisy, and
 * traceable to a missing variable — instead of a dev server that will not boot.
 *
 * The session half is why the matcher is no longer `/api/:path*` alone. That
 * matcher meant the *web app* was open to anyone who found the URL, and since
 * this file attaches the key on their behalf, an open UI was an open API with
 * extra steps.
 */
export async function proxy(request: NextRequest) {
  const { pathname, search } = request.nextUrl;

  // The login form posts here and must work while signed out, by definition.
  if (pathname.startsWith("/auth/")) return NextResponse.next();

  const signedIn = await isValidSession(
    request.cookies.get(SESSION_COOKIE)?.value,
  );

  if (pathname === "/login") {
    if (!signedIn) return NextResponse.next();
    return NextResponse.redirect(new URL("/", request.url));
  }

  if (!signedIn) {
    // An API call gets a status, not a login page. `lib/api/client.ts` would
    // otherwise try to parse HTML as JSON and report something unrelated.
    if (pathname.startsWith("/api/")) {
      return NextResponse.json({ detail: "Not authorised" }, { status: 401 });
    }
    const login = new URL("/login", request.url);
    login.searchParams.set("next", `${pathname}${search}`);
    return NextResponse.redirect(login);
  }

  if (!pathname.startsWith("/api/")) return NextResponse.next();

  // `NextResponse.next({ request: { headers } })`, not
  // `NextResponse.next({ headers })`. The second sets *response* headers, which
  // would send the key to the browser: the exact thing this exists to prevent.
  const headers = new Headers(request.headers);
  headers.set("x-api-key", process.env.API_KEY ?? "");
  return NextResponse.next({ request: { headers } });
}

export const config = {
  /**
   * Everything except Next's own assets and the favicon.
   *
   * `_next/static` and `_next/image` are excluded because they are served to a
   * signed-out browser by definition — the login page is built from them, and
   * redirecting them produces a page with no styles and no bundle. The same
   * trap `CLAUDE.md` records for `allowedDevOrigins`, arrived at from the other
   * direction.
   */
  matcher: ["/((?!_next/static|_next/image|favicon.ico|icon.svg).*)"],
};
