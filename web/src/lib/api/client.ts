/**
 * The one place that knows the API is over HTTP.
 *
 * FastAPI reports every failure as `{"detail": "..."}`, and that string is
 * written to be read by the operator — "Not from a curated feed", "tweet not
 * available: Could not find post". Surfacing it verbatim is what makes a toast
 * worth reading; collapsing it to "Request failed" throws away the only part
 * that says what to do next.
 */

const BASE = "/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    ...init,
    headers: init?.body ? { "Content-Type": "application/json" } : undefined,
  });

  if (!response.ok) {
    throw new Error(await detail(response));
  }
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
