"""The circular inset, found by the AI on Google Images through SerpAPI.

The client's ask (2026-09-14): "Get the AI to source and place the appropriate
image" - the operator was fetching every inset off Google by hand. Not a search
box, which is what a browser tab already is: the AI reads the post, searches,
looks at what came back and places the picture that fits.

**Google Images via SerpAPI, chosen by the operator (2026-09-16)** over Unsplash
(2026-09-15, a day) and Wikimedia Commons (2026-09-16, hours). Both were dropped
for the same reason: a history or news post wants the actual person, place or
event, and stock photography has none of it while Commons has only what someone
donated. Google finds what exists.

**What this does not buy: any right to the pictures.** They belong to whoever
published them, SerpAPI's terms say so, and their legal shield covers scraping
rather than how the results are used. The card carries no credit line. That is
the operator's decision, taken with the trade-off stated.

Three steps, two of them model calls:

1. `name_subject` - a short search query. Skipped on a generate run, where the
   writer has already written one (`DraftContent.inset_subject`).
2. `candidates` - up to six images. No model.
3. `find_for_post` - the model *looks* at them beside the post and picks one, or
   none; `place` then copies the chosen image in.

The filters in `candidates` are what keeps this usable. Google ranks shop
listings, watermarked stock previews and 200px thumbnails alongside the real
picture, and each of those is a circle the operator has to undo by hand.

Rate and cost: a SerpAPI search costs one of the plan's searches (250 a month
free at the time of writing), and an identical search inside an hour is served
from their cache for nothing. A find spends one, a keyword search one.
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

SEARCH_URL = "https://serpapi.com/search.json"

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
    """Google's title for the result, so the operator sees what it is."""
    url: str
    """Google's thumbnail: the swap row's picture, and what the model sees."""
    full_url: str
    """The publisher's own image, which is what gets placed in the circle."""
    source: str
    """Who published it - shown on the swap row, because with Google results the
    operator is the only check on where a picture came from."""


class Found(NamedTuple):
    png: bytes
    subject: str
    chosen: Candidate
    candidates: list[Candidate]
    """Everything the model was shown, the chosen one included."""


class _Subject(BaseModel):
    query: str | None = Field(
        description=(
            "A 1-4 word Google Images search query for the circular picture, or "
            "null when nothing in the post can be pictured."
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


SUBJECT_INSTRUCTIONS = (
    "You write the search query for a small circular picture that sits on a "
    "Facebook post card, searched on Google Images. Name the specific person, "
    "place, object or event when the post has one - for example 'Ignaz "
    "Semmelweis', 'Colosseum', 'Apollo 11', 'chicken tikka masala'. Return null "
    "when nothing in the post can be pictured."
)

PICK_INSTRUCTIONS = (
    "You choose a small circular picture for a Facebook post card. You are shown "
    "the post, then numbered candidate images from Google Images. Pick the one "
    "that best fits the post and still reads when cropped to a small circle: one "
    "clear subject beats a busy scene, and a collage, a chart, a screenshot, a "
    "watermarked stock preview or anything with text or a logo across it is a "
    "poor choice. Return null if none of them fits the post."
)


def _client() -> httpx.Client:
    return httpx.Client(timeout=hero.FETCH_TIMEOUT, follow_redirects=True)


def _key() -> str:
    if not settings.serp_api_key:
        raise InsetError("SERP_API_KEY is not set, so there is nothing to search")
    return settings.serp_api_key


def _public_https(url: str) -> bool:
    try:
        parsed = httpx.URL(url)
    except Exception:  # noqa: BLE001 - a malformed URL is simply not usable
        return False
    host = (parsed.host or "").lower()
    if parsed.scheme != "https" or not host:
        return False
    return not host.startswith(PRIVATE_HOSTS)


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


def candidates(query: str, client: httpx.Client | None = None) -> list[Candidate]:
    """Google Images results for `query`, filtered. Empty is an answer."""
    key = _key()
    client = client or _client()
    try:
        response = client.get(
            SEARCH_URL,
            params={
                "engine": "google_images",
                "q": query,
                "safe": "active",
                "api_key": key,
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
    try:
        body = response.json()
    except ValueError as error:
        raise InsetError("SerpAPI answered something that is not JSON") from error
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
    logger.info('inset search for "{}": {} results, {} kept', query, len(rows), len(found))
    return found


def _download(url: str, client: httpx.Client) -> tuple[bytes, str]:
    """An image's bytes and type, from a public https address.

    Unlike a stock API's CDN this is the open web, so nothing about the host can
    be assumed - hence the size and type checks, and `_public_https` before it.
    """
    if not _public_https(url):
        raise InsetError("only a public https image can be used")
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


def place(candidate: Candidate, client: httpx.Client | None = None) -> bytes:
    """The image as PNG. The drawer's swap.

    The publisher's own file, falling back to Google's thumbnail when that host
    refuses us - a hotlink-blocked original is common enough that losing the
    photo over it would be the failure the operator sees most.
    """
    client = client or _client()
    try:
        data, _ = _download(candidate.full_url, client)
    except InsetError:
        logger.info(
            "inset original refused by {}, using Google's thumbnail",
            httpx.URL(candidate.full_url).host,
        )
        data, _ = _download(candidate.url, client)
    return _png(data)


def name_subject(post: str, model=None) -> str | None:
    """A short search query for the post, or None."""
    answer = writer.ask(post[:POST_CHARS], _Subject, SUBJECT_INSTRUCTIONS, model)
    return (answer.output.query or "").strip() or None


def find_for_post(
    post: str,
    subject: str | None = None,
    client: httpx.Client | None = None,
    model=None,
) -> Found:
    """Search, let the model look, and place the image it chose.

    Raises `InsetError` for every "no image" answer - nothing to picture, nothing
    on Google, nothing that fits, no key - and lets a model failure propagate,
    because the callers answer those differently (a 404 against a 502).
    """
    # Before the model: without a key the search cannot run, and asking Gemini
    # for a query first would spend a call on every press until one is set.
    _key()
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
            f"Image {len(shown)}: {candidate.title} ({candidate.source})",
            BinaryImage(data=data, media_type=kind),
        ]
    if not shown:
        raise InsetError(f"no Google images for “{subject}”")

    def in_range(output: _Pick) -> _Pick:
        if output.choice is not None and not 1 <= output.choice <= len(shown):
            raise ModelRetry(f"`choice` must be between 1 and {len(shown)}, or null.")
        return output

    pick = writer.ask(prompt, _Pick, PICK_INSTRUCTIONS, model, in_range).output
    if pick.choice is None:
        raise InsetError(f"none of the Google images for “{subject}” fit the post", shown)

    chosen = shown[pick.choice - 1]
    return Found(place(chosen, client), subject, chosen, shown)
