"""Shared httpx.Client instances: one per (timeout, follow_redirects) shape.

Every external call used to build a client, use it once, and close it — a TCP
and TLS handshake paid on each request to Metricool, Supabase and the image
CDNs. A client is thread-safe and pools its connections, so one per shape,
created on first use and kept for the life of the process, gets the reuse for
free. Cold paths keep their `with httpx.Client(...)` blocks; the hot paths —
storage, publish, hero and competitor fetches — share.

The `client` parameter every one of those functions accepts is untouched: it is
the test seam, and a caller passing its own still gets exactly that one, never
this cache.
"""

import httpx

_clients: dict[tuple[float, bool], httpx.Client] = {}


def shared(timeout: float, *, follow_redirects: bool = False) -> httpx.Client:
    """The process-wide client for this shape of call.

    Keyed by the two arguments that change behaviour, because the alternative is
    one client whose per-call overrides drift from the defaults each module used
    to set at construction. Two threads racing the miss both build a client and
    one is discarded — wasteful by one object, once, and correct.
    """
    key = (timeout, follow_redirects)
    client = _clients.get(key)
    if client is None:
        client = _clients[key] = httpx.Client(
            timeout=timeout, follow_redirects=follow_redirects
        )
    return client
