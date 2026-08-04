"""The prompt files, read-only.

Read-only on purpose. They are files so that they are reviewable and revertable
in git ([why](../../../docs/data-model.md)); a textarea here would quietly
become the place they are edited, and undo exactly that.

A route rather than a constant in the client because the client's copy drifted:
it went on offering `image_rules.txt` after that file was merged away.
"""

from fastapi import APIRouter
from pydantic import BaseModel

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


@router.get("")
def list_prompts() -> list[PromptFile]:
    return [PromptFile(**file) for file in prompts.list_prompt_files(layout)]
