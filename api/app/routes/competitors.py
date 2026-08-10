"""Which Competitors feed which Pages.

The assignment only. The competitor *list* stays Metricool's and is still never
stored (`CONTEXT.md`) — `GET /sources/competitors/pages` reads it live. What is
stored here is a decision Metricool has no way to express: one competitor
serving several of your Pages.

Why it has to exist is a limit, not a preference. A Metricool account may
configure 100 competitors **in total**. Five Pages that should each watch the
same twenty sources would need those twenty added five times, spending the whole
allowance on twenty distinct sources. So a competitor is added once, under
whichever Page has room, and assigned here to every Page that should read it.

Until a Page has any assignment it falls back to the competitor set it owns in
Metricool — see `routes/sources._visible_to`, which is where that rule lives.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app.db import get_session
from app.models import Page, PageCompetitor

router = APIRouter(prefix="/competitors", tags=["competitors"])


class AssignmentIn(BaseModel):
    """The complete set for a Page. Sent whole, not as add/remove.

    A checkbox list is a set, and sending the set is what makes the request
    idempotent: two clicks racing each other end at the state the second one
    described, rather than at whichever order the deltas happened to arrive in.
    """

    competitor_page_ids: list[str]
    names: dict[str, str] = {}
    """Display names by id, for showing an assignment Metricool no longer lists.
    Optional — a missing name renders as the id, which is ugly but not wrong."""

    notes: dict[str, str] = {}
    """Why this Page reads each competitor, by id. Optional.

    A table has no `git log`, and keeping this mapping in a config file — which
    would have had one — was rejected because it would put the change behind a
    deploy. This is where the reasoning goes instead. An id absent from here
    keeps whatever note it already had rather than losing it, so sending a bare
    set of ids cannot silently erase them.
    """


@router.get("/assignments")
def get_assignments(
    page_id: int,
    session: Session = Depends(get_session),
) -> list[PageCompetitor]:
    if session.get(Page, page_id) is None:
        raise HTTPException(status_code=404, detail=f"No page {page_id}")
    return list(
        session.exec(
            select(PageCompetitor).where(PageCompetitor.page_id == page_id)
        ).all()
    )


@router.put("/assignments")
def set_assignments(
    page_id: int,
    body: AssignmentIn,
    session: Session = Depends(get_session),
) -> list[PageCompetitor]:
    """Replace this Page's assignments with the set given.

    Replace rather than merge, for the reason `AssignmentIn` gives. Removing the
    last one puts the Page back on the Metricool-set fallback, which is a real
    state and not an error: it is what every Page starts in.
    """
    if session.get(Page, page_id) is None:
        raise HTTPException(status_code=404, detail=f"No page {page_id}")

    wanted = {value.strip() for value in body.competitor_page_ids if value.strip()}
    existing = {
        row.competitor_page_id: row
        for row in session.exec(
            select(PageCompetitor).where(PageCompetitor.page_id == page_id)
        ).all()
    }

    for competitor_page_id, row in existing.items():
        if competitor_page_id not in wanted:
            session.delete(row)
            continue
        # Kept rows take an updated note, and keep the one they had when none is
        # sent. A screen that submits the tick list without the notes must not
        # wipe the reasoning as a side effect.
        if competitor_page_id in body.notes:
            row.note = body.notes[competitor_page_id].strip() or None
            session.add(row)

    for competitor_page_id in wanted - existing.keys():
        session.add(
            PageCompetitor(
                page_id=page_id,
                competitor_page_id=competitor_page_id,
                name=body.names.get(competitor_page_id),
                note=(body.notes.get(competitor_page_id) or "").strip() or None,
            )
        )

    session.commit()
    return list(
        session.exec(
            select(PageCompetitor).where(PageCompetitor.page_id == page_id)
        ).all()
    )
