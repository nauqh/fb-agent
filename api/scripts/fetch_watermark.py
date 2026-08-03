"""Rebuild the History Retraced watermark from the page's Facebook avatar.

The original asset is gone. The old rows referenced six watermark objects across
`brand-assets/` and `page-assets/`; every one returns `NoSuchKey`, in all three
buckets, including an `hr` variant filed under a second user id. Supabase Storage
holds 8 objects in total, all draft jpgs from the last few weeks — the older
files were purged. Nothing was ever committed to the old repo either.

So it is re-derived from the page avatar, which Graph serves publicly for a
public page and needs no token:

    https://graph.facebook.com/<page_id>/picture?width=2048

That avatar is dark ink on a white square. Compositing it as-is would paste a
white box onto the hero, so this reproduces the *white* variant the missing file
was named for (`hrwhite.png`): the background becomes transparent, the ink
becomes white, and alpha is taken from ink coverage so antialiased edges survive.
Both are written — the untouched avatar as `-source.png`, for reference.

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


def to_white_on_transparent(source: Image.Image) -> Image.Image:
    """Ink -> white, paper -> transparent, alpha from how dark the pixel was."""
    width, height = source.size
    result = Image.new("RGBA", (width, height))
    target, origin = result.load(), source.load()
    for y in range(height):
        for x in range(width):
            red, green, blue = origin[x, y]
            luminance = (0.299 * red + 0.587 * green + 0.114 * blue) / 255
            target[x, y] = (255, 255, 255, round((1 - luminance) * 255))
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
