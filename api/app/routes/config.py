"""What the renderer is configured with, read back.

`layout.yml` is parsed once at import into a frozen model. Serving that model is
what lets Settings show the values the compositor will actually use, rather than
a copy of them maintained by hand on the other side of the wire — which is what
it was doing, and which drifts the moment either side is edited alone.

Read-only on purpose. Layout is config, not data: it is edited in the file and
reviewed in a diff, for the same reason the prompts are (see docs/decisions.md).
"""

from fastapi import APIRouter

from app.settings import Layout, layout

router = APIRouter(tags=["config"])


@router.get("/layout")
def get_layout() -> Layout:
    """The one Composed Image form. Identical for every Page."""
    return layout
