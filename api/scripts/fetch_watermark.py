"""Rebuild the History Retraced watermark from the page's Facebook avatar.

The original asset is gone. The old rows referenced six watermark objects across
`brand-assets/` and `page-assets/`; every one returns `NoSuchKey`, in all three
buckets, including an `hr` variant filed under a second user id. Supabase Storage
holds 8 objects in total, all draft jpgs from the last few weeks — the older
files were purged. Nothing was ever committed to the old repo either.

So it is re-derived from the page avatar, which Graph serves publicly for a
public page and needs no token:

    https://graph.facebook.com/<page_id>/picture?width=2048

That avatar is the logo in its dark-on-white form: black "istory"/"etraced" with
a red H and R, on a white square. Compositing it as-is would paste a white box
onto the hero, so this reproduces the *white* variant the missing file was named
for (`hrwhite.png`), checked against a real post that still carries the original:

    background   -> transparent
    black ink    -> white
    red ink      -> stays red

The red is the point. A naive "alpha = 1 - luminance" makes the whole mark white,
and because red sits mid-luminance the H and R come out half-transparent grey —
visibly wrong next to the real thing. So pixels are classified by hue first, and
coverage is unmultiplied against the colour each one is *supposed* to reach.

Both files are written; the untouched avatar is kept as `-source.png`.

Output is 217×105 at the avatar's native 247px, and the compositor caps the
watermark at 138px, so there is resolution to spare.

    uv run python scripts/fetch_watermark.py
"""

import sys
from io import BytesIO
from pathlib import Path

import httpx
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.settings import API_DIR  # noqa: E402

FACEBOOK_PAGE_ID = "569035169625026"
OUT_DIR = API_DIR / "assets" / "watermarks"
NAME = "history-retraced"


def fetch_avatar(page_id: str) -> Image.Image:
    response = httpx.get(
        f"https://graph.facebook.com/{page_id}/picture",
        params={"width": 2048, "height": 2048},
        follow_redirects=True,
        timeout=30,
    )
    response.raise_for_status()
    return Image.open(BytesIO(response.content)).convert("RGB")


BRAND_RED = (180, 51, 32)
"""Sampled from the avatar, and confirmed against a real post that still carries
the original watermark — that one reads (180, 45, 26) after JPEG."""


def _luminance(pixel: tuple[int, int, int]) -> float:
    red, green, blue = pixel
    return (0.299 * red + 0.587 * green + 0.114 * blue) / 255


def to_white_on_transparent(source: Image.Image) -> Image.Image:
    """Paper -> transparent, black ink -> white, red ink -> still red.

    Every pixel is a blend of its ink colour over white paper. Coverage is
    recovered by comparing how far the pixel fell from white *relative to how
    far its own ink would take it* — which is why the red needs its own
    denominator: fully-inked red is already at 0.34 luminance, so measuring it
    against black would read as 66% coverage and render the H and R translucent.
    """
    red_ceiling = 1 - _luminance(BRAND_RED)
    width, height = source.size
    result = Image.new("RGBA", (width, height))
    target, origin = result.load(), source.load()

    for y in range(height):
        for x in range(width):
            pixel = origin[x, y]
            red, green, blue = pixel
            is_red = red - green > 40 and red - blue > 40

            darkness = 1 - _luminance(pixel)
            coverage = darkness / red_ceiling if is_red else darkness
            alpha = round(min(1.0, max(0.0, coverage)) * 255)

            target[x, y] = (*BRAND_RED, alpha) if is_red else (255, 255, 255, alpha)

    return result.crop(result.getbbox())


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    avatar = fetch_avatar(FACEBOOK_PAGE_ID)
    avatar.save(OUT_DIR / f"{NAME}-source.png")

    watermark = to_white_on_transparent(avatar)
    watermark.save(OUT_DIR / f"{NAME}.png")

    print(f"avatar    {avatar.size}  {OUT_DIR / f'{NAME}-source.png'}")
    print(f"watermark {watermark.size}  {OUT_DIR / f'{NAME}.png'}")


if __name__ == "__main__":
    main()
