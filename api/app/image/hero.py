"""The generated background. The only part of the composite that costs money.

One call to Gemini's image model per hero. Everything else in `image/` is
arithmetic and rasterising, and can be re-run for free — which is why
`hero_image_path` and `composed_image_path` are separate columns. Editing the
overlay re-composites; it does not re-buy the picture.
"""

import io
import time
from typing import NamedTuple

import httpx
from google import genai
from google.genai import types
from PIL import Image

from app.settings import Layout, settings
from app.settings import layout as default_layout
from app.transient import is_transient
from app.writer import prompts

NO_TEXT_REMINDER = (
    "\n\nREMINDER: Your output must be a photograph with ZERO readable text, "
    "ZERO hashtags, ZERO headline typography, ZERO black bars, and ZERO "
    "post-card layout. Text overlay is composited in post-processing — not by you."
)
"""Appended to every hero prompt, on top of the exclusions in `image.txt`.

Verbatim from `GEMINI_HERO_NO_TEXT_SUFFIX` (`image-prompt.ts:72`). Saying it
twice is not an oversight: the style block goes in as a system instruction and
this rides on the prompt itself, and the one thing that ruins a hero beyond
saving is typography baked into the photograph — the panel is composited over
it, so a headline in the picture is a headline on the post.
"""

SUPPORTED_RATIOS: dict[str, float] = {
    "1:1": 1.0,
    "5:4": 1.25,
    "4:5": 0.8,
    "4:3": 4 / 3,
    "3:4": 0.75,
    "3:2": 1.5,
    "2:3": 2 / 3,
    "16:9": 16 / 9,
    "9:16": 9 / 16,
}
"""What the API accepts. It takes a *ratio*, never a size.

A request for 4:5 came back 928×1152 — the right shape, not the asked-for
pixels. So the hero is always cover-cropped to fit, and the only thing worth
asking for is the ratio closest to the box it has to fill.
"""


class HeroError(RuntimeError):
    """No image came back. Lands on `draft.error`; the draft survives without one."""


FETCH_TIMEOUT = 30.0

MAX_FETCH_BYTES = 16 * 1024 * 1024
"""Bounded because the body is read into memory, and the URL is a publisher's
rather than ours — a feed can point at a 40MB press original."""


def from_url(url: str, client: httpx.Client | None = None) -> bytes:
    """The publisher's own photograph, for a hero nobody has to pay for.

    The Source Item already carries `image_url` and the source cards already
    render it, so this is the cheapest picture in the app: no model call, and
    the rights are whatever the publisher already had.

    **Re-encoded and stored, never hot-linked.** Metricool keeps a *link* to
    what we publish and Facebook fetches it when the post is due, days later —
    the trap `CLAUDE.md` records for our own bucket applies twice over to
    somebody else's CDN, which can rotate a URL or drop the file with no notice.
    Decoding here also means a feed serving an HTML error page is a failure at
    the fetch rather than a broken composite twenty seconds later.

    PNG out, matching what `generate` returns and what the `hero` filename says.
    """
    owned = client is None
    client = client or httpx.Client(timeout=FETCH_TIMEOUT, follow_redirects=True)
    try:
        response = client.get(url)
    except httpx.HTTPError as error:
        raise HeroError(
            f"the feed's image did not answer ({type(error).__name__}): {url}"
        ) from error
    finally:
        if owned:
            client.close()

    if response.is_error:
        raise HeroError(
            f"the feed's image answered {response.status_code}: {url}"
        )
    if len(response.content) > MAX_FETCH_BYTES:
        raise HeroError(
            f"the feed's image is over {MAX_FETCH_BYTES // (1024 * 1024)}MB: {url}"
        )

    try:
        picture = Image.open(io.BytesIO(response.content))
        picture.load()
    except Exception as error:  # noqa: BLE001 — any decode failure is the same answer
        raise HeroError(
            f"the feed's image is not one Pillow can read ({error}): {url}"
        ) from error

    buffer = io.BytesIO()
    picture.convert("RGB").save(buffer, format="PNG")
    return buffer.getvalue()


class Hero(NamedTuple):
    """The picture, and which model actually drew it.

    `model` is part of the result rather than a log line because a fallback
    changes how the picture *looks*. Text from a backup model reads the same;
    a hero from one does not, and a silent swap is a brand drift nobody sees.
    `build_image` turns a swap into a Draft warning.
    """

    data: bytes
    model: str


ATTEMPTS_PER_MODEL = 3
"""Then the next model in the chain.

Three because a 503 "high demand" is usually over in seconds, and the whole
ladder still has to fit inside a run the operator is watching: worst case is
`len(chain) * (3 calls + 3s of sleeping)`.
"""


def _backoff(attempt: int) -> float:
    """1s, then 2s. Exponential, but starting low — this clears fast or not at all."""
    return float(2**attempt)


def aspect_ratio_for(width: int, height: int) -> str:
    """The supported ratio nearest the hero box, so the crop throws away least.

    The box is not the image: the panel grows with the text, so an 896×1120 post
    with a 300px panel leaves an 896×820 hero — 1.09, nearer square than the 4:5
    of the finished picture. Asking for 4:5 there and cropping to fit would
    discard about a quarter of what was paid for.
    """
    target = width / height
    return min(SUPPORTED_RATIOS, key=lambda name: abs(SUPPORTED_RATIOS[name] - target))


def generate(
    prompt: str,
    hero_height_px: int,
    layout: Layout | None = None,
    page_name: str | None = None,
) -> Hero:
    """Image bytes for `prompt`, shaped for the hero box, and the model that drew it.

    **`prompt` is the subject, not the brief.** The brief is `prompts/image.txt`
    — photorealism, mid-shot composition, the card's layers, the exclusions —
    and it is read here rather than passed in, because it was passed in nowhere:
    this function took only the writer's per-draft sentence, so every hero this
    repo has ever drawn was ordered without any of the brand's photography rules.
    `prompts.image_prompt()` had no callers at all. The old system sent the same
    block as `systemInstruction` on every call
    (`facebookImageGenerateService.ts:151`), which is what makes its heroes and
    these comparable.

    **`page_name` picks the brief.** Without it every Page is drawn under
    History Retraced's — reenactment, torchlight, period-accurate dress — which
    is what "the BBTT posts look a bit old, with sepia tone" was. The old tool
    reached the same place by a different route: those Pages stored no image
    prompt and no brand key, and its null-brand fallback was History Retraced
    (`docs/feedback/2026-08-15/old-tool-prompts.md`). Leave it `None` and the
    global file is used, which is correct for a Page that has no directory.

    **A refusal and an outage are not the same failure, and only one is billed.**
    This used to retry neither, on the reasoning that "a second attempt is a
    second charge". That holds for a refusal — the model answered, the answer was
    a well-formed empty response, and Google charged for it. It is simply false
    for a 503: the request never reached a model, so nothing was generated and
    nothing was billed. Retrying it is free, and not retrying it killed runs
    (`writer/agent.py` carries the same scar from the text side).

    So the ladder is: retry the same model while it is *unavailable*, step to the
    next model when it stays that way, and give up instantly on anything else. A
    refusal ends the whole thing on the spot — a second model refuses the same
    prompt for the same reason, and charges again to do it.
    """
    layout = layout or default_layout
    if not settings.gemini_api_key:
        raise HeroError("missing GEMINI_API_KEY")

    client = genai.Client(api_key=settings.gemini_api_key)
    ratio = aspect_ratio_for(layout.image.width, hero_height_px)
    config = types.GenerateContentConfig(
        system_instruction=prompts.image_prompt(layout, page_name),
        response_modalities=["IMAGE"],
        image_config=types.ImageConfig(aspect_ratio=ratio),
    )
    contents = prompt + NO_TEXT_REMINDER

    last: Exception | None = None
    for model in settings.image_fallback_chain:
        for attempt in range(ATTEMPTS_PER_MODEL):
            try:
                response = client.models.generate_content(
                    model=model, contents=contents, config=config
                )
            except Exception as error:  # noqa: BLE001 — reported on the row, not raised at the caller
                # Includes 404 "no longer available", which is how a pinned
                # fallback rots. Not transient, so it surfaces immediately
                # instead of being spent as three attempts and a step sideways.
                if not is_transient(error):
                    raise HeroError(f"{type(error).__name__}: {error}") from error
                last = error
                if attempt < ATTEMPTS_PER_MODEL - 1:
                    time.sleep(_backoff(attempt))
                continue

            for part in _parts(response):
                if part.inline_data is not None and part.inline_data.data:
                    return Hero(part.inline_data.data, model)

            raise HeroError(
                "the model returned no image. Usually a refusal — the prompt names a "
                f"real person, or depicts something the safety filters block: {prompt[:120]!r}"
            )

    raise HeroError(
        f"every image model was unavailable ({', '.join(settings.image_fallback_chain)}), "
        f"{ATTEMPTS_PER_MODEL} attempts each. Last: {type(last).__name__}: {last}"
    )


def _parts(response) -> list:
    """Defensive because a refusal comes back as a well-formed, empty response."""
    for candidate in response.candidates or []:
        if candidate.content and candidate.content.parts:
            return candidate.content.parts
    return []
