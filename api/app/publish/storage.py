"""The one file that leaves this machine: a published composite, as JPEG.

**This is not the `MediaStore` swap `decisions.md` describes.** That framing —
move every image to Supabase and have `save()` return a public URL — was written
before the volumes were measured, and it buys nothing: heroes, insets and the
dozen working composites a draft accumulates while it is being edited are read
by exactly one process, on this machine. Uploading them would put ~37MB of files
nobody will ever fetch into a 1GB bucket, and would mean rewriting the three call
sites that read bytes back through `media.store.path()`.

So local disk stays local, and this is a step in the publish flow instead. One
JPEG, at the moment somebody publishes.

JPEG rather than the stored PNG for the same reason the old system used it
(`quality: 92`, `portrait-inset.ts:79`): measured across the composites in
`api/media/`, PNG averages 1.21MB and JPEG q92 averages 0.27MB of the same
image. Nothing downstream reads the file except Facebook.
"""

import io

import httpx
from PIL import Image

from app.settings import settings

JPEG_QUALITY = 92
"""The old system's number. Visually indistinguishable at feed size, 4.5× smaller."""

TIMEOUT = 60.0
"""Generous: this is a megabyte over a home connection, once per publish."""


class StorageError(RuntimeError):
    """The picture did not reach the bucket, so there is nothing to publish.

    Loud, and raised before anything is sent to Metricool: a scheduled post
    whose image URL 404s is worse than no scheduled post, because it looks
    fine in the planner and goes out broken.
    """


def as_jpeg(png: bytes) -> bytes:
    """Flattened onto white, because JPEG has no alpha.

    The composite is opaque — hero, panel and disc all cover their pixels — so
    this is a formality. It is here anyway: `convert("RGB")` on an image that
    *did* carry alpha composites it onto black without saying so, and a picture
    that silently gained a black edge is exactly the kind of defect that ships.
    """
    source = Image.open(io.BytesIO(png))
    if source.mode in ("RGBA", "LA", "P"):
        flat = Image.new("RGB", source.size, (255, 255, 255))
        source = source.convert("RGBA")
        flat.paste(source, mask=source.split()[-1])
        source = flat
    else:
        source = source.convert("RGB")

    out = io.BytesIO()
    source.save(out, format="JPEG", quality=JPEG_QUALITY)
    return out.getvalue()


def public_url(name: str) -> str:
    """Where the bucket serves `name` from. No signing, and no expiry.

    A signed URL cannot be used here. Metricool stores the link and Facebook
    fetches it when the post is due, so a URL that expires in an hour publishes
    a post with no image — which is why the bucket has to be public rather than
    private-plus-signing.
    """
    root = settings.supabase_url.rstrip("/")
    return f"{root}/storage/v1/object/public/{settings.supabase_bucket}/{name}"


def upload(png: bytes, name: str, client: httpx.Client | None = None) -> str:
    """Convert, upload, and return the public URL. Raises rather than returning None.

    `x-upsert` is on so that re-publishing a draft overwrites its own file
    instead of accumulating one per attempt. The name is the draft's, so two
    drafts cannot collide.
    """
    if not settings.supabase_url or not settings.supabase_service_key:
        raise StorageError(
            "Supabase is not configured. Set SUPABASE_URL and "
            "SUPABASE_SERVICE_KEY — the composite has to be somewhere Metricool "
            "can fetch it."
        )

    body = as_jpeg(png)
    root = settings.supabase_url.rstrip("/")
    owned = client is None
    client = client or httpx.Client(timeout=TIMEOUT)

    try:
        response = client.post(
            f"{root}/storage/v1/object/{settings.supabase_bucket}/{name}",
            content=body,
            headers={
                "Authorization": f"Bearer {settings.supabase_service_key}",
                "Content-Type": "image/jpeg",
                "x-upsert": "true",
            },
        )
    except httpx.HTTPError as error:
        raise StorageError(
            f"the upload did not complete: {type(error).__name__}"
        ) from error
    finally:
        if owned:
            client.close()

    if response.is_error:
        raise StorageError(
            f"Supabase refused the upload ({response.status_code}): "
            f"{response.text[:200]}"
        )

    return public_url(name)
