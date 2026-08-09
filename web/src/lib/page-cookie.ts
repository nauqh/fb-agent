/**
 * The selected Page, shared by the server layout that reads it and the client
 * provider that writes it.
 *
 * In its own module, with no `"use client"`, for the reason `sidebar-cookie.ts`
 * documents at length: a Server Component importing a constant from a client
 * module gets a client reference proxy rather than the string, so
 * `cookies().get(...)` silently looks up `undefined`. Nothing warns. The same
 * mistake here would put every first paint on the wrong Page.
 */
export const PAGE_COOKIE = "fb_page_id";

/**
 * The cookie's value as a Page id, or null when it is absent or junk.
 *
 * Null means "no choice recorded", which the provider resolves to the first
 * Page rather than to a hardcoded 1 — the ids come from the database and a
 * fresh clone need not number them the same way.
 */
export function parsePageCookie(value: string | undefined): number | null {
  if (!value) return null;
  const id = Number(value);
  return Number.isInteger(id) && id > 0 ? id : null;
}
