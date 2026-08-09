/**
 * The rail's collapsed flag, shared by the server layout that reads it and the
 * client component that writes it.
 *
 * In its own module, with no `"use client"`, for a reason that cost an hour:
 * exporting this constant from `components/sidebar.tsx` and importing it into
 * the root layout compiles and typechecks, but a Server Component importing
 * from a client module gets a *client reference proxy* rather than the value.
 * `cookies().get(COLLAPSE_COOKIE)` was therefore looking up `undefined` and
 * quietly returning `false` on every request, so the rail always rendered
 * expanded and snapped shut after hydration — the exact flash the cookie was
 * there to prevent. Nothing warns; the string simply is not there.
 */
export const COLLAPSE_COOKIE = "fb_sidebar_collapsed";
