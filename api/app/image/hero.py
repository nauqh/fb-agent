"""The generated background. The only part of the composite that costs money.

One call to Gemini's image model per hero. Everything else in `image/` is
arithmetic and rasterising, and can be re-run for free — which is why
`hero_image_path` and `composed_image_path` are separate columns. Editing the
overlay re-composites; it does not re-buy the picture.
"""

import time
from typing import NamedTuple

from google import genai
from google.genai import types

from app.settings import Layout, settings
from app.settings import layout as default_layout
from app.transient import is_transient

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


def generate(prompt: str, hero_height_px: int, layout: Layout | None = None) -> Hero:
    """Image bytes for `prompt`, shaped for the hero box, and the model that drew it.

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
        response_modalities=["IMAGE"],
        image_config=types.ImageConfig(aspect_ratio=ratio),
    )

    last: Exception | None = None
    for model in settings.image_fallback_chain:
        for attempt in range(ATTEMPTS_PER_MODEL):
            try:
                response = client.models.generate_content(
                    model=model, contents=prompt, config=config
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
