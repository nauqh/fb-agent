/** The prototype's stand-in for fb_agent.db — reduced to the part that lived. */

type Listener = () => void;
const listeners = new Set<Listener>();

/** Notify anything watching that a table changed. */
export function emit(): void {
  for (const listener of listeners) listener();
}

export function subscribe(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
