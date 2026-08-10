import { NextResponse, type NextRequest } from "next/server";

/**
 * Adds the API key to every proxied request, server-side.
 *
 * `proxy.ts`, not `middleware.ts`: Next 16 renamed the file convention, and a
 * `middleware.ts` is not picked up — it fails silently, as an app that serves
 * fine while every API call comes back 401.
 *
 * This is the half of authentication the browser must never see. `lib/api/
 * client.ts` fetches the relative path `/api/...`, `next.config.ts` rewrites
 * that to FastAPI, and the key is attached here on the way through. So the
 * secret lives in this server's environment and is never in a bundle, a network
 * tab, or a page's HTML.
 *
 * Hence `API_KEY` and not `NEXT_PUBLIC_API_KEY`. The `NEXT_PUBLIC_` prefix
 * inlines a value into the client bundle at build time, which would publish the
 * key to every visitor and undo the whole arrangement.
 *
 * A missing `API_KEY` sends an empty header rather than throwing. The API
 * refuses an empty key, so the failure is 401s on every call — noisy, and
 * traceable to a missing variable — instead of a dev server that will not boot.
 */
export function proxy(request: NextRequest) {
  // `NextResponse.next({ request: { headers } })`, not
  // `NextResponse.next({ headers })`. The second sets *response* headers, which
  // would send the key to the browser: the exact thing this exists to prevent.
  const headers = new Headers(request.headers);
  headers.set("x-api-key", process.env.API_KEY ?? "");
  return NextResponse.next({ request: { headers } });
}

export const config = {
  matcher: "/api/:path*",
};
