import { NextResponse } from "next/server";

import { SESSION_COOKIE } from "@/lib/auth";

/** POST, not GET: a link prefetcher or an image tag must not be able to sign
 *  the operator out. */
export async function POST() {
  const response = NextResponse.json({ ok: true });
  response.cookies.delete(SESSION_COOKIE);
  return response;
}
