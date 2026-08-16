"""The prompts: the files, and a Page's own text over them.

Read-only until 2026-08-17, and the reasoning for that is still right about
what it was aimed at. Prompts are files so they are reviewable and revertable
in git, and the measured failure they were rescued from was **drift between
copies**: three configured pages in the old tool each stored the whole
2,350-character image prompt, 2,030 characters byte-identical, and the copies
went stale while the code moved on.

Two things make a textarea the right answer now rather than the wrong one:

- **Only overrides are stored.** A null column inherits the file; nothing ever
  holds a copy of text it did not change. The drift was between copies of the
  same prompt, and there are no copies.
- **A file cannot be edited in production at all.** Railway's filesystem is
  ephemeral (see `db.py`), so a screen that wrote `prompts/pages/<slug>/x.txt`
  would lose the edit on the next redeploy — silently, and days later. The
  client has been asking for this since F5 (2026-08-15), believing they had
  already written prompts that in fact did not exist.

The global files stay in git and stay the default. What this adds is a Page's
own override, in the one place that survives a deploy.
"""

from datetime import datetime, timezone

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
    """True when this Page is sent something other than the global file.

    The screen has to say so. A Page with its own prompts, shown the global
    body with no marking, is a window that reports the opposite of what the
    model is sent."""

    source: str
    """`page`, `file-override` or `global` — *which* of the three, not just that
    it differs.

    `overridden` alone cannot answer the question the operator is about to act
    on. Editing text that is in fact inherited creates an override they did not
    ask for; a `file-override` cannot be edited from here at all and, on
    Railway, could not have been written from here either."""

    editable: bool
    """False for any prompt with no column behind it — see `prompts.COLUMN`."""


class PromptEdit(BaseModel):
    body: str
    """The Page's own text. **Blank clears the override** and returns the Page to
    the inherited file, which is the only sane reading of an emptied textarea:
    storing `""` would send the model no system prompt at all."""


@router.get("")
def list_prompts(
    page_id: int | None = None, session: Session = Depends(get_session)
) -> list[PromptFile]:
    """The prompts as sent. `page_id` resolves the per-Page overrides.

    Omitting it returns the global files, which is what a Page without its own
    directory or stored text is sent anyway.
    """
    page = None
    if page_id is not None:
        page = session.get(Page, page_id)
        if page is None:
            raise HTTPException(404, "page not found")
    return [
        PromptFile(**file)
        for file in prompts.list_prompt_files(
            layout, page.name if page else None, page
        )
    ]


@router.put("/{page_id}/{filename}")
def set_prompt(
    page_id: int,
    filename: str,
    edit: PromptEdit,
    session: Session = Depends(get_session),
) -> PromptFile:
    """Give one Page its own text for one prompt, or clear it back to the file.

    Per Page only — there is no route that edits a global. The globals are the
    reviewed default and belong in git; making them editable here is what would
    reopen the drift the file layout was chosen to prevent, because every Page
    reads them.
    """
    page = session.get(Page, page_id)
    if page is None:
        raise HTTPException(404, "page not found")
    column = prompts.COLUMN.get(filename)
    if column is None:
        raise HTTPException(
            422,
            f"{filename!r} has no per-Page column. Editable: "
            f"{', '.join(sorted(prompts.COLUMN))}.",
        )

    setattr(page, column, edit.body.strip() or None)
    page.updated_at = datetime.now(timezone.utc)
    session.add(page)
    session.commit()
    session.refresh(page)

    resolved = prompts.list_prompt_files(layout, page.name, page)
    return PromptFile(**next(f for f in resolved if f["filename"] == filename))
