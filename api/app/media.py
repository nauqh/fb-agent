"""Where image bytes live: a Supabase Storage bucket, and only that.

`save(data, name) -> stored` returns a path *relative to the bucket*, and that
relative path is what a Draft row holds. Rows never hold a URL: the project and
the bucket are config, so moving either is an env change rather than an UPDATE
across every row. `public_url` turns a stored path into the link the browser and
Facebook fetch.

There is one implementation, and the Protocol stays anyway — the test suite
substitutes a filesystem-backed fake (`tests/conftest.py`), which is what keeps
244 tests offline and fast instead of mocking HTTP to write a file.

The bucket is **public and unsigned**, which is load-bearing rather than lazy.
Metricool stores the image *link* and Facebook fetches it when the post is due,
which can be days later. The old app signed for 24h
(`social-agent/src/lib/facebook/metricool-media.ts:17`) and 0 of its 105
published posts still have a working image. Public here means "public to
whoever holds the link": buckets do not list, and `filename` ends every name
with six random hex characters.
"""

import re
import time
from datetime import datetime, timezone
from typing import Protocol
from uuid import uuid4

import httpx

from app.settings import settings

_SAFE = re.compile(r"[^a-z0-9]+")

TIMEOUT = 60.0
"""Generous. Every write is roughly a megabyte, and dev talks to the same cloud."""

ATTEMPTS = 3
BACKOFF_SECONDS = 0.5

CONTENT_TYPES = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg"}
"""Exactly what the bucket accepts — see `allowed_mime_types` in `supabase/buckets.sql`."""


class MediaError(RuntimeError):
    """The bytes did not reach the bucket, or did not come back out of it.

    Loud. A picture that silently failed to store leaves a row pointing at
    nothing, and the row is what the review screen and the publish step trust.
    """


class MediaStore(Protocol):
    """Everything the app does to an image, and nothing it does not.

    `read` and `delete` are on here because four call sites used to reach past
    this Protocol for `path()` and touch the filesystem themselves — the hero
    and inset reads in `generate`, the composite read in `publish`, and the
    unlink in `delete_draft`. A seam every caller steps around is not a seam,
    and it was exactly what would have had to be rewritten to move off disk.
    """

    def save(self, data: bytes, name: str) -> str:
        """Return the stored path, relative to the store's root."""
        ...

    def read(self, stored: str) -> bytes:
        """The bytes back. Raises if the path is not there.

        Loud on a miss, because every caller is about to draw with these bytes
        and the alternative is a composite built on nothing.
        """
        ...

    def delete(self, stored: str) -> None:
        """Gone, and silent if it was already gone.

        Idempotent on purpose: `delete_draft` runs over three columns that may
        never have been filled, and a re-run of a half-finished cleanup must not
        fail on the files it already removed.
        """
        ...


class SupabaseMediaStore:
    """Stores `<yyyy-mm>/<name>` in the bucket named by `SUPABASE_BUCKET`.

    The month prefix survived the move off disk for a smaller reason than it was
    introduced with: object storage has no directories to keep short, but
    Supabase's dashboard renders a prefix as a folder, and finding a draft's
    files by hand is otherwise a scroll through everything ever written.

    Dev and production use **different buckets**, and that is not tidiness. The
    two have separate databases, so both hand out draft id 1, 2, 3 — one bucket
    would mean a laptop test overwriting the picture a scheduled post points at.

    Config is read per call rather than at construction: `store` is built at
    import, and at import time `.env` may not have been loaded yet.
    """

    def __init__(
        self, bucket: str | None = None, client: httpx.Client | None = None
    ) -> None:
        self._bucket = bucket
        self._client = client

    @property
    def bucket(self) -> str:
        return self._bucket or settings.supabase_bucket

    def save(self, data: bytes, name: str) -> str:
        stored = f"{datetime.now(timezone.utc).strftime('%Y-%m')}/{name}"
        self._call(
            "POST",
            stored,
            content=data,
            headers={"Content-Type": _content_type(name), "x-upsert": "true"},
        )
        return stored

    def read(self, stored: str) -> bytes:
        return self._call("GET", stored).content

    def delete(self, stored: str) -> None:
        self._call("DELETE", stored, missing_ok=True)

    def _call(
        self, method: str, stored: str, *, missing_ok: bool = False, **kwargs
    ) -> httpx.Response:
        if not settings.supabase_url or not settings.supabase_service_key:
            raise MediaError(
                "Supabase is not configured. Set SUPABASE_URL and "
                "SUPABASE_SERVICE_KEY — there is nowhere else for images to go."
            )

        root = settings.supabase_url.rstrip("/")
        url = f"{root}/storage/v1/object/{self.bucket}/{stored}"
        headers = {"Authorization": f"Bearer {settings.supabase_service_key}"}
        headers.update(kwargs.pop("headers", {}))

        owned = self._client is None
        client = self._client or httpx.Client(timeout=TIMEOUT)
        try:
            response = _attempt(client, method, url, headers, kwargs)
        finally:
            if owned:
                client.close()

        if response.status_code == 404 and missing_ok:
            return response
        if response.is_error:
            raise MediaError(
                f"Supabase refused {method} {stored} "
                f"({response.status_code}): {response.text[:200]}"
            )
        return response


def _attempt(
    client: httpx.Client, method: str, url: str, headers: dict, kwargs: dict
) -> httpx.Response:
    """Retry a blip, never a refusal.

    Writing to disk effectively never failed, so nothing upstream was written to
    survive a failed write. Over a network it fails routinely, and two of the
    three kinds of file cannot simply be made again: the hero was paid for, and
    the inset is a file a person picked off their own machine.

    A dropped connection or a timeout is worth another go. A 4xx is an answer —
    a bad key, a file over the bucket's size limit, a mime type it will not take
    — and repeating it three times only delays the error by a second and a half.
    5xx retries with the transport errors: it is the same "not now".
    """
    last: Exception | None = None

    for attempt in range(ATTEMPTS):
        try:
            response = client.request(method, url, headers=headers, **kwargs)
        except httpx.HTTPError as error:
            last = error
        else:
            if response.status_code < 500:
                return response
            last = MediaError(f"{response.status_code}: {response.text[:200]}")

        if attempt + 1 < ATTEMPTS:
            time.sleep(BACKOFF_SECONDS * (attempt + 1))

    raise MediaError(
        f"{method} did not complete after {ATTEMPTS} attempts: "
        f"{type(last).__name__}: {last}"
    )


def _content_type(name: str) -> str:
    """From the extension, and refused if it is not one the bucket takes.

    Refusing here rather than letting Supabase answer is about the *other*
    failure: a JPEG written under a `.png` name uploads happily and is then
    served as `image/png`, which some fetchers will not decode. The mismatch
    would surface as a broken image on a live post, days later.
    """
    extension = name.rsplit(".", 1)[-1].lower()
    if extension not in CONTENT_TYPES:
        raise MediaError(
            f"{name!r} is not a kind of file this bucket takes "
            f"({', '.join(sorted(CONTENT_TYPES))})."
        )
    return CONTENT_TYPES[extension]


def public_url(stored: str) -> str:
    """Where the bucket serves `stored` from. No signing, and no expiry.

    Built server-side and handed to the client on the Draft, rather than
    assembled in React from a `NEXT_PUBLIC_` variable as the old app did
    (`social-agent/src/lib/facebook/media-url.ts`). One place knows the bucket.

    No escaping: every segment comes from `filename`, which emits digits, ASCII
    letters, hyphens and one dot.
    """
    root = settings.supabase_url.rstrip("/")
    return f"{root}/storage/v1/object/public/{settings.supabase_bucket}/{stored}"


def watermark_source(upload_path: str | None, asset_path: str | None) -> str | bytes | None:
    """The mark to stamp on this Page's cards. An upload wins over the asset.

    The upload is fetched here rather than inside the compositor, which draws
    and does no IO — `store.read` raises loudly on a miss, and the caller turns
    that into a failed draft with a sentence in it. That is the whole difference
    from the old system, which hosted its watermarks, swallowed the `NoSuchKey`
    when the bucket was cleared, and printed the page name as text for months.

    Returns the committed asset's *path* untouched: it is a file in the image,
    so there is nothing to fetch and no failure to have.
    """
    if upload_path:
        return store.read(upload_path)
    return asset_path


def filename(draft_id: int, kind: str, extension: str) -> str:
    """`42-hero-20260806T141230-a3f9c1.png` — draft first, so a listing sorts usefully.

    Timestamped rather than overwritten: regenerating a hero for a draft whose
    composite is already approved must not silently change the approved picture.

    `extension` has no default. It used to be `"png"`, which stopped being safe
    once composites became JPEG — a caller that forgot the argument would write
    JPEG bytes under a `.png` name, and `_content_type` would then label them
    `image/png`.
    """
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    # Seconds are not fine enough: re-compositing twice in one second produced
    # the same name, so the second write overwrote the first and the row still
    # pointed at a path whose contents had changed underneath it.
    return (
        f"{draft_id}-{_SAFE.sub('-', kind.lower()).strip('-')}-"
        f"{stamp}-{uuid4().hex[:6]}.{extension}"
    )


store: MediaStore = SupabaseMediaStore()
