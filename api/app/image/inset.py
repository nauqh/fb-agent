"""The circular inset, found by the AI - on Google Images or Unsplash, per Page.

The client's ask (2026-09-14): "Get the AI to source and place the appropriate
image" - the operator was fetching every inset off Google by hand. Not a search
box, which is what a browser tab already is: the AI reads the post, searches,
looks at what came back and places the picture that fits.

**Two sources, chosen per Page (`page.inset_source`, 2026-09-16).** Unsplash was
first (2026-09-15) and then replaced by Google through SerpAPI, because a history
or news post wants the actual person, place or event and stock photography has
none of it. That was right for those Pages and wrong for the rest: a fitness or
recipe Page wants "barbell squat" and "chicken tikka masala", which is exactly
what stock is for, and Google's answer there is shop listings and blog clutter.
So the Page decides, and both searches stay.

They differ in more than the URL:

- **Google** is searched by *name* ("Ignaz Semmelweis") and has to be filtered
  hard - shop listings, watermarked stock previews and listing-sized thumbnails
  rank above the real picture. It confers **no right to the pictures**: they
  belong to whoever published them, and the card carries no credit line. The
  operator took that trade-off with it stated.
- **Unsplash** is searched by *what a photograph could show* ("hand washing"),
  because it has nothing of named people. Its photos are free to use, and its
  API guidelines ask for a download ping when one is used, which `place` sends.

Three steps, two of them model calls:

1. `name_subject` - a short search query, worded for the Page's source.
2. `candidates` - up to six images. No model.
3. `find_for_post` - the model *looks* at them beside the post and picks one, or
   none; `place` then copies the chosen image in.

Cost: a Google search spends one SerpAPI search (250 a month free at the time
of writing; an identical search inside an hour is cached and free). Unsplash is
free and allows 50 requests an hour on a demo key; a find spends two (search,
download ping).
"""

import io
from typing import Literal, NamedTuple

import httpx
from PIL import Image
from pydantic import BaseModel, Field
from pydantic_ai import ModelRetry
from pydantic_ai.messages import BinaryImage

from app.image import hero
from app.log import logger
from app.settings import settings
from app.writer import agent as writer

InsetSource = Literal["google", "unsplash"]

LABEL: dict[str, str] = {"google": "Google", "unsplash": "Unsplash"}
"""What the operator reads in an error. A message that said "no images" without
saying where was the one that sent people to check the wrong key."""

# --- Google, through SerpAPI -------------------------------------------------

SERPAPI_URL = "https://serpapi.com/search.json"

BROWSER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0 Safari/537.36"
)
"""Sent when fetching a publisher's own image. These are ordinary web pages'
assets rather than an API's, and a bare client UA is refused by enough hosts to
be worth avoiding."""

PRIVATE_HOSTS = ("localhost", "127.", "0.", "10.", "192.168.", "169.254.", "::1")
"""A `full_url` arrives from the browser on a swap, so the fetch is only as
narrow as this check. `https` plus these prefixes keeps it off this machine and
off a private network; Google's results are public web addresses."""

STOCK_SOURCES = (
    "getty",
    "alamy",
    "shutterstock",
    "istock",
    "dreamstime",
    "123rf",
    "depositphotos",
    "adobe stock",
)
"""Dropped by `source`. These rank well and serve a watermarked preview, which
is both unusable as a picture and the clearest case of taking someone's work."""

MIN_WIDTH_PX = 600
"""Smaller than this is a listing thumbnail. The circle is drawn at up to about
half the card's width, and an upscaled 200px image looks like a mistake."""

# --- Unsplash ----------------------------------------------------------------

UNSPLASH_URL = "https://api.unsplash.com/search/photos"

UNSPLASH_API_HOST = "api.unsplash.com"

UNSPLASH_IMAGE_HOSTS = {"images.unsplash.com"}
"""Where free photos are served from. Unsplash+ premium photos come from
`plus.unsplash.com` and are not ours to use, so this host check is also the
premium filter - and, on a swap, what keeps a browser-sent candidate on
Unsplash."""

# --- both --------------------------------------------------------------------

CANDIDATES = 6
"""Images kept - what the model chooses among, and the drawer's swap row."""

VISION_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
"""What Gemini accepts as an image part."""

POST_CHARS = 3000
"""How much of the post the model reads. Enough to know the subject; the rest of
a long first comment adds tokens, not judgement."""


class InsetError(RuntimeError):
    """No usable image. A warning on the draft, or a 4xx from the drawer.

    `candidates` is what was offered when the answer was "none of these fit":
    the operator may still like one, so the callers keep them on the draft.
    """

    def __init__(self, message: str, candidates: list["Candidate"] | None = None):
        super().__init__(message)
        self.candidates = candidates or []


class Candidate(BaseModel):
    title: str
    """The result's own description, so the operator sees what it is."""
    url: str
    """The small image: the swap row's picture, and what the model sees."""
    full_url: str
    """The large image, which is what gets placed in the circle."""
    source: str = ""
    """Who published it (Google) or "Unsplash". Shown on the swap row, because
    with Google results the operator is the only check on where it came from."""
    download_location: str | None = None
    """Unsplash only: pinged when the photo is placed, as their guidelines ask."""


class Found(NamedTuple):
    png: bytes
    subject: str
    chosen: Candidate
    candidates: list[Candidate]
    """Everything the model was shown, the chosen one included."""


class _Subject(BaseModel):
    query: str | None = Field(
        description=(
            "A 1-4 word image search query for the circular picture, or null "
            "when nothing in the post can be pictured."
        )
    )


class _Pick(BaseModel):
    choice: int | None = Field(
        description=(
            "The number of the image that fits the post best, or null when none "
            "of them does."
        )
    )
    reason: str = Field(description="One short sentence on why.")


SUBJECT_INSTRUCTIONS: dict[str, str] = {
    "google": (
        "You write the search query for a small circular picture that sits on a "
        "Facebook post card, searched on Google Images. Name the specific person, "
        "place, object or event when the post has one - for example 'Ignaz "
        "Semmelweis', 'Colosseum', 'Apollo 11', 'chicken tikka masala'. Return "
        "null when nothing in the post can be pictured."
    ),
    "unsplash": (
        "You write the search query for a small circular stock photo that sits on "
        "a Facebook post card. Stock photos show real, generic things, not "
        "specific people from history: describe what a photograph could show that "
        "fits the post - for example 'hand washing', 'colosseum rome', 'chicken "
        "tikka masala', 'barbell squat'. Return null when nothing in the post can "
        "be photographed."
    ),
}

PICK_INSTRUCTIONS: dict[str, str] = {
    "google": (
        "You choose a small circular picture for a Facebook post card. You are "
        "shown the post, then numbered candidate images from Google Images. Pick "
        "the one that best fits the post and still reads when cropped to a small "
        "circle: one clear subject beats a busy scene, and a collage, a chart, a "
        "screenshot, a watermarked stock preview or anything with text or a logo "
        "across it is a poor choice. Return null if none of them fits the post."
    ),
    "unsplash": (
        "You choose a small circular photo for a Facebook post card. You are shown "
        "the post, then numbered candidate photos from Unsplash, each with its "
        "description. Pick the one that best fits the post and still reads when "
        "cropped to a small circle: one clear subject beats a busy scene, and a "
        "photo with text or a logo in it is a poor choice. Return null if none of "
        "them fits the post."
    ),
}


def _client() -> httpx.Client:
    return httpx.Client(timeout=hero.FETCH_TIMEOUT, follow_redirects=True)


def _require_key(source: str) -> None:
    """Before any request, and before the model is asked for a query."""
    if source == "unsplash":
        if not settings.unsplash_access_key:
            raise InsetError("UNSPLASH_ACCESS_KEY is not set, so there is nothing to search")
    elif not settings.serp_api_key:
        raise InsetError("SERP_API_KEY is not set, so there is nothing to search")


def _unsplash_auth() -> dict[str, str]:
    """Sent to `api.unsplash.com` only, never to the image CDN."""
    return {
        "Authorization": f"Client-ID {settings.unsplash_access_key}",
        "Accept-Version": "v1",
    }


def _public_https(url: str) -> bool:
    try:
        parsed = httpx.URL(url)
    except Exception:  # noqa: BLE001 - a malformed URL is simply not usable
        return False
    host = (parsed.host or "").lower()
    if parsed.scheme != "https" or not host:
        return False
    return not host.startswith(PRIVATE_HOSTS)


def _on(url: str, hosts: set[str]) -> bool:
    try:
        parsed = httpx.URL(url)
    except Exception:  # noqa: BLE001 - a malformed URL is simply not ours
        return False
    return parsed.scheme == "https" and parsed.host in hosts


def _json(response: httpx.Response, label: str) -> dict:
    try:
        return response.json()
    except ValueError as error:
        raise InsetError(f"{label} answered something that is not JSON") from error


def _wanted(row: dict) -> bool:
    """Google's ranking is not ours. See `STOCK_SOURCES` and `MIN_WIDTH_PX`."""
    if row.get("is_product"):
        return False
    source = str(row.get("source") or "").lower()
    if any(stock in source for stock in STOCK_SOURCES):
        return False
    if int(row.get("original_width") or 0) < MIN_WIDTH_PX:
        return False
    return _public_https(row.get("thumbnail") or "") and _public_https(row.get("original") or "")


def _google(query: str, client: httpx.Client) -> tuple[int, list[Candidate]]:
    try:
        response = client.get(
            SERPAPI_URL,
            params={
                "engine": "google_images",
                "q": query,
                "safe": "active",
                "api_key": settings.serp_api_key,
            },
        )
    except httpx.HTTPError as error:
        raise InsetError(f"SerpAPI did not answer ({type(error).__name__})") from error
    if response.status_code == 401:
        raise InsetError("SerpAPI refused the key - check SERP_API_KEY")
    if response.status_code == 429:
        raise InsetError("SerpAPI's searches for this plan are used up")
    if response.is_error:
        raise InsetError(f"SerpAPI answered {response.status_code}")
    body = _json(response, "SerpAPI")
    # Their own field, and the only place a refusal shows on a 200.
    if body.get("error"):
        raise InsetError(f"SerpAPI: {body['error']}"[:200])

    rows = body.get("images_results") or []
    found = []
    for row in rows:
        if not _wanted(row):
            continue
        found.append(
            Candidate(
                title=str(row.get("title") or "Untitled image").strip()[:120],
                url=row["thumbnail"],
                full_url=row["original"],
                source=str(row.get("source") or "unknown").strip()[:60],
            )
        )
        if len(found) == CANDIDATES:
            break
    return len(rows), found


def _unsplash(query: str, client: httpx.Client) -> tuple[int, list[Candidate]]:
    try:
        response = client.get(
            UNSPLASH_URL,
            params={"query": query, "per_page": str(CANDIDATES), "content_filter": "high"},
            headers=_unsplash_auth(),
        )
    except httpx.HTTPError as error:
        raise InsetError(f"Unsplash did not answer ({type(error).__name__})") from error
    if response.status_code == 401:
        raise InsetError("Unsplash refused the access key - check UNSPLASH_ACCESS_KEY")
    if response.status_code == 403:
        raise InsetError("Unsplash's hourly request limit is used up - try again later")
    if response.is_error:
        raise InsetError(f"Unsplash answered {response.status_code}")

    results = _json(response, "Unsplash").get("results", []) or []
    found = []
    for photo in results:
        urls = photo.get("urls") or {}
        small, regular = urls.get("small") or "", urls.get("regular") or ""
        download = (photo.get("links") or {}).get("download_location") or ""
        if not (
            _on(small, UNSPLASH_IMAGE_HOSTS)
            and _on(regular, UNSPLASH_IMAGE_HOSTS)
            and _on(download, {UNSPLASH_API_HOST})
        ):
            continue
        found.append(
            Candidate(
                title=(photo.get("alt_description") or photo.get("description") or "Untitled photo")
                .strip()[:120],
                url=small,
                full_url=regular,
                source="Unsplash",
                download_location=download,
            )
        )
    return len(results), found


def candidates(
    query: str, client: httpx.Client | None = None, *, source: InsetSource = "google"
) -> list[Candidate]:
    """Images for `query` from the Page's source, filtered. Empty is an answer."""
    _require_key(source)
    client = client or _client()
    search = _unsplash if source == "unsplash" else _google
    total, found = search(query, client)
    logger.info(
        'inset search ({}) for "{}": {} results, {} kept', source, query, total, len(found)
    )
    return found


def _download(url: str, client: httpx.Client, hosts: set[str] | None = None) -> tuple[bytes, str]:
    """An image's bytes and type.

    `hosts` pins the fetch to one CDN (Unsplash). Without it any public https
    address is allowed, which is what Google results are - hence the size and
    type checks, and `_public_https` before any of it.
    """
    allowed = _on(url, hosts) if hosts else _public_https(url)
    if not allowed:
        raise InsetError(
            "only an Unsplash photo can be used" if hosts else "only a public https image can be used"
        )
    try:
        response = client.get(url, headers={"User-Agent": BROWSER_AGENT})
        response.raise_for_status()
    except httpx.HTTPError as error:
        raise InsetError(
            f"that image could not be downloaded ({type(error).__name__})"
        ) from error
    kind = (response.headers.get("content-type") or "").split(";")[0].strip().lower()
    if not kind.startswith("image/") or not response.content:
        raise InsetError(f"that URL answered {kind or 'nothing'} rather than an image")
    if len(response.content) > hero.MAX_FETCH_BYTES:
        raise InsetError("that image is too large")
    return response.content, kind


def _png(data: bytes) -> bytes:
    """Re-encoded rather than stored as sent, like an upload."""
    try:
        picture = Image.open(io.BytesIO(data))
        picture.load()
    except Exception as error:
        raise InsetError(f"that image did not decode ({error})") from error
    buffer = io.BytesIO()
    picture.convert("RGB").save(buffer, format="PNG")
    return buffer.getvalue()


def place(
    candidate: Candidate, client: httpx.Client | None = None, *, source: InsetSource = "google"
) -> bytes:
    """The image as PNG. The drawer's swap, and the last step of a find.

    Google: the publisher's own file, falling back to Google's thumbnail when
    that host refuses us - hotlink blocking is common enough that losing the
    picture over it would be the failure the operator meets most.

    Unsplash: both URLs checked against Unsplash before anything is fetched,
    then the download ping their guidelines ask for. The ping cannot lose the
    photo - it is bookkeeping, and a failure is logged, not raised.
    """
    client = client or _client()
    if source == "unsplash":
        if not _on(candidate.download_location or "", {UNSPLASH_API_HOST}):
            raise InsetError("only an Unsplash photo can be used")
        data, _ = _download(candidate.full_url, client, UNSPLASH_IMAGE_HOSTS)
        png = _png(data)
        try:
            client.get(candidate.download_location, headers=_unsplash_auth()).raise_for_status()
        except httpx.HTTPError as error:
            logger.warning("unsplash download ping failed for {}: {}", candidate.full_url, error)
        return png

    try:
        data, _ = _download(candidate.full_url, client)
    except InsetError:
        logger.info(
            "inset original refused by {}, using Google's thumbnail",
            httpx.URL(candidate.full_url).host,
        )
        data, _ = _download(candidate.url, client)
    return _png(data)


def name_subject(post: str, model=None, *, source: InsetSource = "google") -> str | None:
    """A short search query for the post, worded for the source, or None."""
    answer = writer.ask(post[:POST_CHARS], _Subject, SUBJECT_INSTRUCTIONS[source], model)
    return (answer.output.query or "").strip() or None


def find_for_post(
    post: str,
    subject: str | None = None,
    client: httpx.Client | None = None,
    model=None,
    *,
    source: InsetSource = "google",
) -> Found:
    """Search, let the model look, and place the image it chose.

    Raises `InsetError` for every "no image" answer - nothing to picture, nothing
    found, nothing that fits, no key - and lets a model failure propagate,
    because the callers answer those differently (a 404 against a 502).
    """
    # Before the model: without a key the search cannot run, and asking Gemini
    # for a query first would spend a call on every press until one is set.
    _require_key(source)
    subject = (subject or "").strip() or name_subject(post, model, source=source)
    if not subject:
        raise InsetError("nothing in the post can be photographed")

    label = LABEL[source]
    hosts = UNSPLASH_IMAGE_HOSTS if source == "unsplash" else None
    client = client or _client()
    shown: list[Candidate] = []
    prompt: list = [f"THE POST:\n{post[:POST_CHARS]}", f"CANDIDATES for “{subject}”:"]
    for candidate in candidates(subject, client, source=source):
        try:
            data, kind = _download(candidate.url, client, hosts)
        except InsetError:
            continue
        if kind not in VISION_TYPES:
            continue
        shown.append(candidate)
        prompt += [
            f"Image {len(shown)}: {candidate.title} ({candidate.source})",
            BinaryImage(data=data, media_type=kind),
        ]
    if not shown:
        raise InsetError(f"no {label} images for “{subject}”")

    def in_range(output: _Pick) -> _Pick:
        if output.choice is not None and not 1 <= output.choice <= len(shown):
            raise ModelRetry(f"`choice` must be between 1 and {len(shown)}, or null.")
        return output

    pick = writer.ask(prompt, _Pick, PICK_INSTRUCTIONS[source], model, in_range).output
    if pick.choice is None:
        raise InsetError(f"none of the {label} images for “{subject}” fit the post", shown)

    chosen = shown[pick.choice - 1]
    return Found(place(chosen, client, source=source), subject, chosen, shown)
