/**
 * The one place that knows the API is over HTTP.
 *
 * FastAPI reports every failure as `{"detail": "..."}`, and that string is
 * written to be read by the operator — "Not from a curated feed", "tweet not
 * available: Could not find post". Surfacing it verbatim is what makes a toast
 * worth reading; collapsing it to "Request failed" throws away the only part
 * that says what to do next.
 */

import { emit } from "@/lib/store";

const BASE = "/api";

/**
 * A write, and therefore something every open query needs to hear about.
 *
 * `use-query.ts` re-reads on this notification, which is what keeps two views
 * of the same row in step: the Review queue and an open Draft are separate
 * queries, so approving inside the sheet used to refresh only the sheet and
 * leave the queue showing "Pending review" until a reload.
 *
 * It fires here rather than in `api/drafts.ts` so it cannot be forgotten on
 * the next endpoint — the method already says whether a call mutates.
 */
function mutated(method?: string): void {
  if (method && method !== "GET") emit();
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    ...init,
    // Only for a JSON string body. A `FormData` body must go out without this:
    // the browser sets `multipart/form-data` *plus the boundary*, and a
    // hand-written Content-Type has no boundary, so the server parses nothing.
    headers:
      typeof init?.body === "string"
        ? { "Content-Type": "application/json" }
        : undefined,
  });

  if (!response.ok) {
    throw new Error(await detail(response));
  }
  mutated(init?.method);
  return response.json() as Promise<T>;
}

async function detail(response: Response): Promise<string> {
  try {
    const body = await response.json();
    // 422 from FastAPI's own body validation is an array of field errors
    // rather than a string, and it means the client sent the wrong shape.
    if (typeof body.detail === "string") return body.detail;
    if (Array.isArray(body.detail)) {
      return body.detail.map((issue: { msg: string }) => issue.msg).join("; ");
    }
  } catch {
    // Non-JSON body — the status line is all there is.
  }
  return `${response.status} ${response.statusText}`;
}

export function get<T>(path: string, params?: Record<string, string | number>): Promise<T> {
  const query = params
    ? `?${new URLSearchParams(
        Object.entries(params).map(([key, value]) => [key, String(value)]),
      )}`
    : "";
  return request<T>(`${path}${query}`);
}

export function post<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, { method: "POST", body: JSON.stringify(body) });
}

export function patch<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, { method: "PATCH", body: JSON.stringify(body) });
}

/** A file, as multipart. The one request in the app that does not send JSON. */
export function upload<T>(path: string, file: File): Promise<T> {
  const body = new FormData();
  body.append("file", file);
  return request<T>(path, { method: "POST", body });
}

/** No return type: this DELETE answers 204, which has no body to parse. */
export async function del(path: string): Promise<void> {
  const response = await fetch(`${BASE}${path}`, { method: "DELETE" });
  if (!response.ok) throw new Error(await detail(response));
  // Its own `fetch`, so it misses the notification in `request`.
  mutated("DELETE");
}

/** For a DELETE that answers with the row it changed rather than 204. */
export function delJson<T>(path: string): Promise<T> {
  return request<T>(path, { method: "DELETE" });
}
