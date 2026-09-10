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
from sqlmodel import Session, select

from app.db import get_session
from app.models import Draft, Page, PromptTemplate
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
    body: str | None
    """The Page's own text. `null` clears the override and returns the Page to
    the inherited file. A non-null blank keeps the new overlay semantics: for
    `overlay.txt` an empty string is the explicit no-overlay opt-out (see
    `prompts.stored`), for the other two it clears like `null`."""


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

    # Three states, and they have to stay distinct: `None` is "back to the
    # file", `""` on overlay.txt is the no-overlay opt-out (`prompts.stored`),
    # and text is the override. For system/image an empty box clears like
    # `None` — an emptied textarea there has never meant anything else.
    if edit.body is None:
        setattr(page, column, None)
    elif filename == "overlay.txt":
        setattr(page, column, edit.body.strip())
    else:
        setattr(page, column, edit.body.strip() or None)
    page.updated_at = datetime.now(timezone.utc)
    session.add(page)
    session.commit()
    session.refresh(page)

    resolved = prompts.list_prompt_files(layout, page.name, page)
    return PromptFile(**next(f for f in resolved if f["filename"] == filename))


# --- the template library ----------------------------------------------------
#
# The client's 2026-08-20 request: named post styles, each carrying its own
# system/overlay/image text, selectable at run time. One rule from everything
# above carries over unchanged: **a template stores deltas, never copies.**
# Blank inherits the Page's chain; a template that restated the whole house
# prompt would be a copy that drifts.
#
# Its own sub-router, registered before `router` in `main.py`: `PUT
# /templates/{id}` under the router above would match `/{page_id}/{filename}`
# first and die on `page_id` not being an integer.

templates_router = APIRouter(prefix="/prompts/templates", tags=["prompts"])


class TemplateBody(BaseModel):
    name: str
    page_id: int
    """The Page the style belongs to — every style is one Page's."""
    system_prompt: str | None = None
    overlay_prompt: str | None = None
    image_prompt: str | None = None


class TemplateOut(TemplateBody):
    id: int
    """What the screens read back; `TemplateBody` alone is what they send."""


def _template_out(row: PromptTemplate) -> TemplateOut:
    return TemplateOut(
        id=row.id,
        name=row.name,
        page_id=row.page_id,
        system_prompt=row.system_prompt,
        overlay_prompt=row.overlay_prompt,
        image_prompt=row.image_prompt,
    )


@templates_router.get("")
def list_templates(
    page_id: int | None = None, session: Session = Depends(get_session)
) -> list[TemplateOut]:
    """With `page_id`, that Page's styles only — styles are per-Page (client,
    2026-09-10). Without it, everything, for screens that have not picked a
    Page yet."""
    query = select(PromptTemplate)
    if page_id is not None:
        query = query.where(PromptTemplate.page_id == page_id)
    return [_template_out(row) for row in session.exec(query).all()]


@templates_router.post("", status_code=201)
def create_template(
    body: TemplateBody, session: Session = Depends(get_session)
) -> TemplateOut:
    name = body.name.strip()
    if not name:
        raise HTTPException(422, "A template needs a name.")
    if not any(
        (text or "").strip()
        for text in (body.system_prompt, body.overlay_prompt, body.image_prompt)
    ):
        raise HTTPException(
            422,
            "A template with all three prompts blank changes nothing — it "
            "would only add a dropdown entry. Leave the prompts blank by not "
            "creating it.",
        )
    if session.exec(
        select(PromptTemplate).where(PromptTemplate.name == name)
    ).first():
        raise HTTPException(409, f"A template named {name!r} already exists.")
    if body.page_id is not None and session.get(Page, body.page_id) is None:
        raise HTTPException(404, f"No Page {body.page_id}")
    row = PromptTemplate(
        name=name,
        page_id=body.page_id,
        system_prompt=body.system_prompt,
        overlay_prompt=body.overlay_prompt,
        image_prompt=body.image_prompt,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return _template_out(row)


@templates_router.put("/{template_id}")
def update_template(
    template_id: int,
    body: TemplateBody,
    session: Session = Depends(get_session),
) -> TemplateOut:
    row = session.get(PromptTemplate, template_id)
    if row is None:
        raise HTTPException(404, f"No template {template_id}")
    name = body.name.strip()
    if not name:
        raise HTTPException(422, "A template needs a name.")
    clash = session.exec(
        select(PromptTemplate).where(PromptTemplate.name == name)
    ).first()
    if clash and clash.id != template_id:
        raise HTTPException(409, f"A template named {name!r} already exists.")

    row.name = name
    row.system_prompt = body.system_prompt
    row.overlay_prompt = body.overlay_prompt
    row.image_prompt = body.image_prompt
    session.add(row)
    session.commit()
    session.refresh(row)
    return _template_out(row)


@templates_router.delete("/{template_id}", status_code=204)
def delete_template(template_id: int, session: Session = Depends(get_session)) -> None:
    row = session.get(PromptTemplate, template_id)
    if row is None:
        raise HTTPException(404, f"No template {template_id}")

    # Drafts that were generated under this style keep their text; only the
    # pointer goes. A dangling id would make the next rewrite fail on a lookup
    # the operator cannot fix from any screen.
    for draft in session.exec(
        select(Draft).where(Draft.prompt_template_id == template_id)
    ).all():
        draft.prompt_template_id = None
        session.add(draft)
    session.delete(row)
    session.commit()
