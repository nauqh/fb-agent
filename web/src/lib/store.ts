/** The prototype's stand-in for fb_agent.db - reduced to the part that lived. */

type Listener = () => void;
const listeners = new Set<Listener>();
const progressListeners = new Set<Listener>();
let pendingRequests = 0;

/** Notify anything watching that a table changed. */
export function emit(): void {
  for (const listener of listeners) listener();
}

/** Mark an API request as visible work for the global progress indicator. */
export function beginRequest(): void {
  pendingRequests += 1;
  for (const listener of progressListeners) listener();
}

/** Finish visible API work, including failed requests. */
export function endRequest(): void {
  pendingRequests = Math.max(0, pendingRequests - 1);
  for (const listener of progressListeners) listener();
}

export function hasPendingRequests(): boolean {
  return pendingRequests > 0;
}

export function subscribe(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function subscribeProgress(listener: Listener): () => void {
  progressListeners.add(listener);
  return () => progressListeners.delete(listener);
}
