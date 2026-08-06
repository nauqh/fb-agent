"""The generated background. The only part of the composite that costs money.

One call to Gemini's image model per hero. Everything else in `image/` is
arithmetic and rasterising, and can be re-run for free — which is why
`hero_image_path` and `composed_image_path` are separate columns. Editing the
overlay re-composites; it does not re-buy the picture.
"""

from google import genai
from google.genai import types

from app.settings import Layout
from app.settings import layout as default_layout
from app.settings import settings

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


def aspect_ratio_for(width: int, height: int) -> str:
    """The supported ratio nearest the hero box, so the crop throws away least.

    The box is not the image: the panel grows with the text, so an 896×1120 post
    with a 300px panel leaves an 896×820 hero — 1.09, nearer square than the 4:5
    of the finished picture. Asking for 4:5 there and cropping to fit would
    discard about a quarter of what was paid for.
    """
    target = width / height
    return min(SUPPORTED_RATIOS, key=lambda name: abs(SUPPORTED_RATIOS[name] - target))


def generate(prompt: str, hero_height_px: int, layout: Layout | None = None) -> bytes:
    """Image bytes for `prompt`, shaped for the hero box.

    No fallback chain, unlike the writer. There is one image model configured
    and a second attempt is a second charge, so a failure is reported rather
    than retried — the operator decides whether the prompt was worth paying for
    twice.
    """
    layout = layout or default_layout
    if not settings.gemini_api_key:
        raise HeroError("missing GEMINI_API_KEY")

    client = genai.Client(api_key=settings.gemini_api_key)
    ratio = aspect_ratio_for(layout.image.width, hero_height_px)

    try:
        response = client.models.generate_content(
            model=settings.gemini_image_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE"],
                image_config=types.ImageConfig(aspect_ratio=ratio),
            ),
        )
    except Exception as error:  # noqa: BLE001 — reported on the row, not raised at the caller
        raise HeroError(f"{type(error).__name__}: {error}") from error

    for part in _parts(response):
        if part.inline_data is not None and part.inline_data.data:
            return part.inline_data.data

    raise HeroError(
        "the model returned no image. Usually a refusal — the prompt names a "
        f"real person, or depicts something the safety filters block: {prompt[:120]!r}"
    )


def _parts(response) -> list:
    """Defensive because a refusal comes back as a well-formed, empty response."""
    for candidate in response.candidates or []:
        if candidate.content and candidate.content.parts:
            return candidate.content.parts
    return []
