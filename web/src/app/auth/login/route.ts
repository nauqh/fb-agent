import { NextResponse, type NextRequest } from "next/server";

import { SESSION_COOKIE, SESSION_MAX_AGE, issueSession, matches } from "@/lib/auth";

/**
 * `/auth/login`, not `/api/auth/login`.
 *
 * `next.config.ts` rewrites every `/api/*` path to FastAPI, so a route handler
 * under `/api` would never run — the request would be proxied to Python, which
 * has no such endpoint, and the login form would get a 404 from a file that is
 * plainly there.
 *
 * The credentials live in this server's environment and are compared here.
 * Nothing about them reaches the browser, which is the same arrangement the API
 * key already has.
 */
export async function POST(request: NextRequest) {
  const { email, password } = await request.json().catch(() => ({
    email: "",
    password: "",
  }));

  const ok =
    matches(String(email ?? "").trim(), process.env.APP_EMAIL ?? "") &&
    matches(String(password ?? ""), process.env.APP_PASSWORD ?? "");

  if (!ok) {
    // One message for both fields. Saying *which* was wrong tells an attacker
    // when they have found the address, and there is only one to find.
    return NextResponse.json(
      { error: "That email and password do not match." },
      { status: 401 },
    );
  }

  const response = NextResponse.json({ ok: true });
  response.cookies.set(SESSION_COOKIE, await issueSession(), {
    httpOnly: true,
    sameSite: "lax",
    // Railway terminates TLS, so this is on in production and off locally,
    // where `localhost` is not a secure origin and the cookie would be dropped.
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: SESSION_MAX_AGE,
  });
  return response;
}
