"""The prompt files, read-only.

Read-only on purpose. They are files so that they are reviewable and revertable
in git ([why](../../../docs/data-model.md)); a textarea here would quietly
become the place they are edited, and undo exactly that.

A route rather than a constant in the client because the client's copy drifted:
it went on offering `image_rules.txt` after that file was merged away.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from app.db import get_session
from app.models import Page
from app.settings import layout
from app.writer import prompts

router = APIRouter(prefix="/prompts", tags=["prompts"])


class PromptFile(BaseModel):
    filename: str
    chars: int
    body: str
    """As substituted from `layout.yml`, not as typed — a raw `{panel_pct}` on
    screen would not tell the operator whether the prompt and the compositor
    agree."""
    overridden: bool
    """True when this Page has its own copy under `prompts/pages/<slug>/`.

    The screen has to say so. A Page with its own prompts, shown the global
    body with no marking, is a window that reports the opposite of what the
    model is sent."""


@router.get("")
def list_prompts(
    page_id: int | None = None, session: Session = Depends(get_session)
) -> list[PromptFile]:
    """The prompts as sent. `page_id` resolves the per-Page overrides.

    Omitting it returns the global files, which is what a Page without its own
    directory is sent anyway.
    """
    page_name = None
    if page_id is not None:
        page = session.get(Page, page_id)
        if page is None:
            raise HTTPException(404, "page not found")
        page_name = page.name
    return [
        PromptFile(**file) for file in prompts.list_prompt_files(layout, page_name)
    ]
