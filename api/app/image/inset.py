"""The circular inset, found by the AI on Unsplash rather than uploaded.

The client's ask (2026-09-14): "Get the AI to source and place the appropriate
image" - the operator was fetching every inset off Google by hand. Not a search
box, which is what a browser tab already is: the AI reads the post, searches,
looks at what came back and places the photo that fits. **Not Google**: the
Custom Search JSON API is closed to new customers and switched off 2027-01-01.

**Unsplash, chosen over Wikipedia (2026-09-15).** It is stock photography, so it
has real photographs of "hand washing" and "barbell squat" and nothing of
Ignaz Semmelweis - which is why the query the model writes describes what a
photograph could show, not who the story is about.

Three steps, two of them model calls:

1. `name_subject` - a short photo search query. Skipped on a generate run, where
   the writer has already written one (`DraftContent.inset_subject`).
2. `candidates` - up to six photos. No model.
3. `find_for_post` - the model *looks* at them beside the post and picks one, or
   none; `place` then copies the chosen photo in.

**Unsplash's API guidelines, and where each is met** (read 2026-09-14):

- "use the hotlinked image URLs returned by the API" when displaying - the
  drawer's swap row shows `urls.small` straight from Unsplash.
- "something similar to a download (like when a user chooses the image to
  include in a blog post…) … must send a request to the download endpoint" -
  `place` does, for every photo placed, pick or swap. A photo chosen for a post
  is that example, and it is also why copying the bytes is allowed: the card is
  a composite in our bucket that Facebook fetches days later, the Metricool trap
  `CLAUDE.md` records.
- "attribute Unsplash, the Unsplash photographer, and … a link back to their
  Unsplash profile" - **not done, by the operator's decision (2026-09-15)**: a
  credit line under the swap row was built and removed. Unsplash reviews
  attribution before raising a demo app's 50-requests-an-hour limit, so it
  comes back if that limit has to be raised.

Rate: a demo app gets 50 JSON requests an hour; files on `images.unsplash.com`
do not count. A find spends two (search, download ping), a swap one.
"""

import io
from typing import NamedTuple

import httpx
from PIL import Image
from pydantic import BaseModel, Field
from pydantic_ai import ModelRetry
from pydantic_ai.messages import BinaryImage

from app.image import hero
from app.log import logger
from app.settings import settings
from app.writer import agent as writer

SEARCH_URL = "https://api.unsplash.com/search/photos"

API_HOST = "api.unsplash.com"

IMAGE_HOSTS = {"images.unsplash.com"}
"""Where free photos are served from. Unsplash+ premium photos come from
`plus.unsplash.com` and are not ours to use, so this host check is also the
premium filter. It guards our own fetches too: a swap sends a candidate back
from the browser, and an open fetch would make the API call arbitrary hosts."""

CANDIDATES = 6
"""Photos searched - what the model chooses among, and the drawer's swap row."""

VISION_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
"""What Gemini accepts as an image part."""

POST_CHARS = 3000
"""How much of the post the model reads. Enough to know the subject; the rest of
a long first comment adds tokens, not judgement."""


class InsetError(RuntimeError):
    """No usable photo. A warning on the draft, or a 4xx from the drawer.

    `candidates` is what was offered when the answer was "none of these fit":
    the operator may still like one, so the callers keep them on the draft.
    """

    def __init__(self, message: str, candidates: list["Candidate"] | None = None):
        super().__init__(message)
        self.candidates = candidates or []


class Candidate(BaseModel):
    title: str
    """Unsplash's description of the photo, so the operator sees what it is."""
    url: str
    """`urls.small`, 400px: the swap row's thumbnail, and what the model sees."""
    full_url: str
    """`urls.regular`, 1080px: what is placed in the circle."""
    download_location: str
    """Pinged when this photo is placed - the guidelines' download event."""


class Found(NamedTuple):
    png: bytes
    subject: str
    chosen: Candidate
    candidates: list[Candidate]
    """Everything the model was shown, the chosen one included."""


class _Subject(BaseModel):
    query: str | None = Field(
        description=(
            "A 1-4 word stock photo search query for the circular photo, or "
            "null when nothing in the post can be photographed."
        )
    )


class _Pick(BaseModel):
    choice: int | None = Field(
        description=(
            "The number of the photo that fits the post best, or null when none "
            "of them does."
        )
    )
    reason: str = Field(description="One short sentence on why.")


SUBJECT_INSTRUCTIONS = (
    "You write the search query for a small circular stock photo that sits on a "
    "Facebook post card. Stock photos show real, generic things, not specific "
    "people from history: describe what a photograph could show that fits the "
    "post - for example 'hand washing', 'colosseum rome', 'chicken tikka "
    "masala', 'barbell squat'. Return null when nothing in the post can be "
    "photographed."
)

PICK_INSTRUCTIONS = (
    "You choose a small circular photo for a Facebook post card. You are shown "
    "the post, then numbered candidate photos from Unsplash, each with its "
    "description. Pick the one that best fits the post and still reads when "
    "cropped to a small circle: one clear subject beats a busy scene, and a "
    "photo with text or a logo in it is a poor choice. Return null if none of "
    "them fits the post."
)


def _client() -> httpx.Client:
    return httpx.Client(timeout=hero.FETCH_TIMEOUT, follow_redirects=True)


def _auth() -> dict[str, str]:
    """Sent to `api.unsplash.com` only, never to the image CDN."""
    if not settings.unsplash_access_key:
        raise InsetError("UNSPLASH_ACCESS_KEY is not set, so there is nothing to search")
    return {
        "Authorization": f"Client-ID {settings.unsplash_access_key}",
        "Accept-Version": "v1",
    }


def _on(url: str, hosts: set[str]) -> bool:
    try:
        parsed = httpx.URL(url)
    except Exception:  # noqa: BLE001 - a malformed URL is simply not ours
        return False
    return parsed.scheme == "https" and parsed.host in hosts


def candidates(query: str, client: httpx.Client | None = None) -> list[Candidate]:
    """Free photos for `query`, in Unsplash's relevance order. Empty is an answer."""
    headers = _auth()
    client = client or _client()
    try:
        response = client.get(
            SEARCH_URL,
            params={"query": query, "per_page": str(CANDIDATES), "content_filter": "high"},
            headers=headers,
        )
    except httpx.HTTPError as error:
        raise InsetError(f"Unsplash did not answer ({type(error).__name__})") from error
    if response.status_code == 401:
        raise InsetError("Unsplash refused the access key - check UNSPLASH_ACCESS_KEY")
    if response.status_code == 403:
        raise InsetError("Unsplash's hourly request limit is used up - try again later")
    if response.is_error:
        raise InsetError(f"Unsplash answered {response.status_code}")
    try:
        results = response.json().get("results", [])
    except ValueError as error:
        raise InsetError("Unsplash answered something that is not JSON") from error

    found = []
    for photo in results:
        urls = photo.get("urls") or {}
        small, regular = urls.get("small") or "", urls.get("regular") or ""
        download = (photo.get("links") or {}).get("download_location") or ""
        if not (_on(small, IMAGE_HOSTS) and _on(regular, IMAGE_HOSTS) and _on(download, {API_HOST})):
            continue
        found.append(
            Candidate(
                title=(photo.get("alt_description") or photo.get("description") or "Untitled photo")
                .strip()[:120],
                url=small,
                full_url=regular,
                download_location=download,
            )
        )
    return found


def _download(url: str, client: httpx.Client) -> tuple[bytes, str]:
    """A photo's bytes and type, from the Unsplash CDN and nowhere else."""
    if not _on(url, IMAGE_HOSTS):
        raise InsetError("only an Unsplash photo can be used")
    try:
        response = client.get(url)
        response.raise_for_status()
    except httpx.HTTPError as error:
        raise InsetError(
            f"that photo could not be downloaded ({type(error).__name__})"
        ) from error
    kind = (response.headers.get("content-type") or "").split(";")[0].strip().lower()
    if not kind.startswith("image/") or not response.content:
        raise InsetError(f"that URL answered {kind or 'nothing'} rather than a photo")
    if len(response.content) > hero.MAX_FETCH_BYTES:
        raise InsetError("that photo is too large")
    return response.content, kind


def _png(data: bytes) -> bytes:
    """Re-encoded rather than stored as sent, like an upload."""
    try:
        picture = Image.open(io.BytesIO(data))
        picture.load()
    except Exception as error:
        raise InsetError(f"that photo did not decode ({error})") from error
    buffer = io.BytesIO()
    picture.convert("RGB").save(buffer, format="PNG")
    return buffer.getvalue()


def place(candidate: Candidate, client: httpx.Client | None = None) -> bytes:
    """The photo as PNG, with Unsplash told it was used. The drawer's swap.

    Both URLs are checked before anything is fetched: a swap's candidate comes
    back from the browser. The download ping cannot lose the photo - it is
    bookkeeping owed to Unsplash, and a failure is logged, not raised.
    """
    if not _on(candidate.download_location, {API_HOST}):
        raise InsetError("only an Unsplash photo can be used")
    client = client or _client()
    data, _ = _download(candidate.full_url, client)
    png = _png(data)
    try:
        client.get(candidate.download_location, headers=_auth()).raise_for_status()
    except (httpx.HTTPError, InsetError) as error:
        logger.warning("unsplash download ping failed for {}: {}", candidate.full_url, error)
    return png


def name_subject(post: str, model=None) -> str | None:
    """A short photo search query for the post, or None."""
    answer = writer.ask(post[:POST_CHARS], _Subject, SUBJECT_INSTRUCTIONS, model)
    return (answer.output.query or "").strip() or None


def find_for_post(
    post: str,
    subject: str | None = None,
    client: httpx.Client | None = None,
    model=None,
) -> Found:
    """Search, let the model look, and place the photo it chose.

    Raises `InsetError` for every "no photo" answer - nothing to photograph,
    nothing on Unsplash, nothing that fits, no key - and lets a model failure
    propagate, because the callers answer those differently (a 404 against a
    502).
    """
    # Before the model: without a key the search cannot run, and asking Gemini
    # for a query first would spend a call on every press until one is set.
    _auth()
    subject = (subject or "").strip() or name_subject(post, model)
    if not subject:
        raise InsetError("nothing in the post can be photographed")

    client = client or _client()
    shown: list[Candidate] = []
    prompt: list = [f"THE POST:\n{post[:POST_CHARS]}", f"CANDIDATES for “{subject}”:"]
    for candidate in candidates(subject, client):
        try:
            data, kind = _download(candidate.url, client)
        except InsetError:
            continue
        if kind not in VISION_TYPES:
            continue
        shown.append(candidate)
        prompt += [
            f"Photo {len(shown)}: {candidate.title}",
            BinaryImage(data=data, media_type=kind),
        ]
    if not shown:
        raise InsetError(f"no Unsplash photos for “{subject}”")

    def in_range(output: _Pick) -> _Pick:
        if output.choice is not None and not 1 <= output.choice <= len(shown):
            raise ModelRetry(f"`choice` must be between 1 and {len(shown)}, or null.")
        return output

    pick = writer.ask(prompt, _Pick, PICK_INSTRUCTIONS, model, in_range).output
    if pick.choice is None:
        raise InsetError(f"none of the Unsplash photos for “{subject}” fit the post", shown)

    chosen = shown[pick.choice - 1]
    return Found(place(chosen, client), subject, chosen, shown)
