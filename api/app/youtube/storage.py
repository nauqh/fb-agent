"""Where processed videos and uploaded CTA clips live: their own Supabase bucket.

The image MediaStore (`app/media.py`) is image-only — the bucket it talks to
(`SUPABASE_BUCKET`) accepts exactly `image/png` and `image/jpeg`, which is the
whole contract those files have. Videos are a different kind of file with a
different size ceiling, so they get their own bucket
(`SUPABASE_YOUTUBE_BUCKET`, default `youtube-media`) and this store.

The shape is otherwise the image store's, deliberately: same relative-path
storage, same month prefix, same retry-on-blip, same "public means public to
whoever holds the link". That last one is the same load-bearing rule as the
images — Metricool stores the *URL* and YouTube/Instagram fetch the file when
the post is due, possibly days later. A signed URL would expire first, which is
exactly what killed the old app's videos (the images doc records the same
failure).

The bucket must accept `video/mp4` — see `supabase/buckets.sql` for the
committed bucket rows (applied by hand, like the media bucket).
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

from app.settings import settings

TIMEOUT = 60.0
ATTEMPTS = 3
BACKOFF_SECONDS = 0.5

CONTENT_TYPES = {"mp4": "video/mp4"}


class YoutubeStoreError(RuntimeError):
    """The bytes did not reach the bucket, or did not come back out of it.

    Loud, for the same reason `MediaError` is: a video that silently failed to
    store leaves the job row pointing at nothing, and the row is what the
    schedule route and the operator trust.
    """


class SupabaseYoutubeStore:
    """`<yyyy-mm>/<name>` in the bucket named by `SUPABASE_YOUTUBE_BUCKET`.

    `save` is the one extra step over the image store: it rejects content that
    is not an mp4 *before* the http call, because a JPEG written under a `.mp4`
    name uploads happily and is then served as `video/mp4`, which some fetchers
    will not decode — the mismatch surfaces as a broken reel days later.
    """

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client

    def save(self, data: bytes, name: str) -> str:
        if not name.lower().endswith(".mp4"):
            raise YoutubeStoreError(
                f"{name!r} is not an mp4. This bucket only takes mp4 files."
            )
        stored = f"{datetime.now(timezone.utc).strftime('%Y-%m')}/{name}"
        self._call(
            "POST",
            stored,
            content=data,
            headers={"Content-Type": "video/mp4", "x-upsert": "true"},
        )
        return stored

    def read(self, stored: str) -> bytes:
        return self._call("GET", stored).content

    def delete(self, stored: str) -> None:
        self._call("DELETE", stored, missing_ok=True)

    def exists(self, stored: str) -> bool:
        """Whether the object is in the bucket. A HEAD, not a GET — the caller
        only wants the answer, and a processed video is megabytes."""
        try:
            self._call("HEAD", stored)
        except YoutubeStoreError:
            return False
        return True

    def signed_upload_url(self, stored: str) -> str:
        """A URL the **browser** can PUT this object to without any credential.

        The reason this exists is Vercel: a CTA clip uploaded through the app
        crosses Vercel's serverless request-body ceiling (about 4.5MB) and
        comes back 413 in production long before the 50MB the bucket allows.
        So the bytes go browser → Supabase directly, and the API's part is a
        small JSON call: mint a token for a path it chose.

        The mint is `POST /object/upload/sign/{bucket}/{path}` with the service
        key; the browser consumes the returned relative URL — **resolved
        against `/storage/v1`, not the project root** — with `PUT` and the
        token as its Bearer. Both were found by experiment, not docs: the
        storage server re-signs instead of storing if the request arrives as
        POST, and every wrong shape answers 404 "Bucket not found" because
        the upload token has no role claim and the handler's bucket lookup
        runs as anon.

        Running as anon is also why two RLS policies exist for this bucket
        (see supabase/buckets.sql): objects INSERT and buckets SELECT. The
        service key bypasses RLS; an upload token does not.
        """
        if not settings.supabase_url or not settings.supabase_service_key:
            raise YoutubeStoreError(
                "Supabase is not configured. Set SUPABASE_URL and "
                "SUPABASE_SERVICE_KEY — there is nowhere else for videos to go."
            )
        root = settings.supabase_url.rstrip("/")
        owned = self._client is None
        client = self._client or httpx.Client(timeout=TIMEOUT)
        try:
            response = client.post(
                f"{root}/storage/v1/object/upload/sign/"
                f"{settings.supabase_youtube_bucket}/{stored}",
                json={},
                headers={
                    "Authorization": f"Bearer {settings.supabase_service_key}",
                },
            )
        except httpx.HTTPError as error:
            raise YoutubeStoreError(
                f"Supabase did not answer the upload sign: {type(error).__name__}"
            ) from error
        finally:
            if owned:
                client.close()
        if response.is_error:
            raise YoutubeStoreError(
                f"Supabase refused the upload sign ({response.status_code}): "
                f"{response.text[:200]}"
            )
        relative = response.json().get("url")
        if not relative:
            raise YoutubeStoreError("Supabase returned no upload url")
        return f"{root}/storage/v1{relative}"

    def public_url(self, stored: str) -> str:
        root = settings.supabase_url.rstrip("/")
        return (
            f"{root}/storage/v1/object/public/"
            f"{settings.supabase_youtube_bucket}/{stored}"
        )

    def _call(
        self, method: str, stored: str, *, missing_ok: bool = False, **kwargs
    ) -> httpx.Response:
        if not settings.supabase_url or not settings.supabase_service_key:
            raise YoutubeStoreError(
                "Supabase is not configured. Set SUPABASE_URL and "
                "SUPABASE_SERVICE_KEY — there is nowhere else for videos to go."
            )
        root = settings.supabase_url.rstrip("/")
        url = f"{root}/storage/v1/object/{settings.supabase_youtube_bucket}/{stored}"
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
            raise YoutubeStoreError(
                f"Supabase refused {method} {stored} "
                f"({response.status_code}): {response.text[:200]}"
            )
        return response


class DirectoryYoutubeStore:
    """`SupabaseYoutubeStore`'s shape, backed by a directory. Tests and dev only.

    Lives beside the real store rather than in the suite because the Shorts dev
    server (`scripts/shorts_dev_server.py`) needs exactly this and cannot import
    a conftest — it was copy-pasted into three files before it moved here.

    `base_url` is what separates the two callers. The suite wants a URL that is
    never fetched (`https://bucket.example/...`, the default); the dev server
    wants one that really resolves, so it passes the address of the little
    static server it runs over the same directory.
    """

    def __init__(self, root: str, base_url: str = "https://bucket.example") -> None:
        self.root = Path(root)
        self.base_url = base_url.rstrip("/")

    def save(self, data: bytes, name: str) -> str:
        stored = f"{datetime.now(timezone.utc).strftime('%Y-%m')}/{name}"
        target = self.root / stored
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return stored

    def read(self, stored: str) -> bytes:
        return (self.root / stored).read_bytes()

    def delete(self, stored: str) -> None:
        (self.root / stored).unlink(missing_ok=True)

    def public_url(self, stored: str) -> str:
        return f"{self.base_url}/{stored}"

    def signed_upload_url(self, stored: str) -> str:
        raise YoutubeStoreError(
            "Signed browser uploads need Supabase; the directory store has no "
            "token to hand out. Run against the real bucket to upload clips."
        )

    def exists(self, stored: str) -> bool:
        return (self.root / stored).exists()


def _attempt(
    client: httpx.Client, method: str, url: str, headers: dict, kwargs: dict
) -> httpx.Response:
    """Retry a blip, never a refusal — the image store's rule, repeated.

    A dropped connection is worth another go; a 4xx is an answer and repeating
    it three times only delays the error. 5xx retries with the transport errors:
    it is the same "not now".
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
            last = YoutubeStoreError(f"{response.status_code}: {response.text[:200]}")

        if attempt + 1 < ATTEMPTS:
            time.sleep(BACKOFF_SECONDS * (attempt + 1))

    raise YoutubeStoreError(
        f"{method} did not complete after {ATTEMPTS} attempts: "
        f"{type(last).__name__}: {last}"
    )


store = SupabaseYoutubeStore()