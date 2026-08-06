"""Where image bytes go. One adapter, on purpose.

`save(data, name) -> path` writes under `media_root`, which `main.py` already
serves at `/media`. The stored value is the *relative* path, so moving the root
or serving it from somewhere else does not rewrite every row.

Normally one implementation means the seam is imaginary and should not exist.
It is here because the second one is scheduled rather than imagined: Metricool
fetches the image URL from its own servers, so the v2 push cannot work against
local disk and will need Supabase Storage or R2. That costs one Protocol and one
class today.
"""

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from app.settings import settings

_SAFE = re.compile(r"[^a-z0-9]+")


class MediaStore(Protocol):
    def save(self, data: bytes, name: str) -> str:
        """Return the stored path, relative to the store's root."""
        ...


class LocalMediaStore:
    """Writes `media_root/<yyyy-mm>/<name>`, served from `/media`.

    Bucketed by month so a year of drafts is not one directory listing, and
    because it makes "delete everything before March" a directory removal.
    """

    def __init__(self, root: str | None = None) -> None:
        self.root = Path(root or settings.media_root)

    def save(self, data: bytes, name: str) -> str:
        bucket = datetime.now(timezone.utc).strftime("%Y-%m")
        target = self.root / bucket / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return f"{bucket}/{name}"

    def path(self, stored: str) -> Path:
        return self.root / stored


def filename(draft_id: int, kind: str, extension: str = "png") -> str:
    """`42-hero-20260806T141230.png` — draft first, so a listing sorts usefully.

    Timestamped rather than overwritten: regenerating a hero for a draft whose
    composite is already approved must not silently change the approved picture.
    """
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    # Seconds are not fine enough: re-compositing twice in one second produced
    # the same name, so the second write overwrote the first and the row still
    # pointed at a path whose contents had changed underneath it.
    return (
        f"{draft_id}-{_SAFE.sub('-', kind.lower()).strip('-')}-"
        f"{stamp}-{uuid4().hex[:6]}.{extension}"
    )


store = LocalMediaStore()
