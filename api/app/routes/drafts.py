"""Generate a run, then read and edit what it produced.

`POST /generate` returns ids immediately and fills the rows in the background;
the client polls `GET /drafts/{id}` until `status` leaves `generating`. The row
is the job record, which is why progress lives on it.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session, select

from app import generate
from app.db import get_session
from app.models import Draft, DraftStatus, SourceItemBase

router = APIRouter(tags=["drafts"])


class GenerateRequest(BaseModel):
    """Source Items **by value**, which is what makes generate the only write.

    The Cart holds items rather than row ids, so nothing is stored until a run
    uses it. `generate.resolve_sources` decides which kinds may be authored by
    the client and which must already exist.
    """

    page_ids: list[int]
    sources: list[SourceItemBase] = []
    topic: str | None = None


@router.post("/generate", status_code=202)
def start_generate(
    request: GenerateRequest,
    background: BackgroundTasks,
    session: Session = Depends(get_session),
) -> list[int]:
    """202: accepted, not finished. One real draft took ~130s."""
    try:
        draft_ids = generate.start_run(
            session, request.page_ids, request.sources, request.topic
        )
    except generate.GenerateError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    background.add_task(generate.run_drafts, draft_ids)
    return draft_ids


@router.get("/drafts")
def list_drafts(
    status: DraftStatus | None = Query(None),
    page_id: int | None = Query(None),
    session: Session = Depends(get_session),
) -> list[Draft]:
    query = select(Draft)
    if status is not None:
        query = query.where(Draft.status == status)
    if page_id is not None:
        query = query.where(Draft.page_id == page_id)
    return list(session.exec(query.order_by(Draft.created_at.desc())).all())  # type: ignore[union-attr]


@router.get("/drafts/{draft_id}")
def get_draft(draft_id: int, session: Session = Depends(get_session)) -> Draft:
    draft = session.get(Draft, draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail=f"No draft {draft_id}")
    return draft


class DraftEdit(BaseModel):
    """The written fields only. Status moves through its own routes.

    `image_prompt` is here because it is the only lever on a hero the model
    refused — the writer produced it, so the operator has to be able to correct
    it before paying for another generation.
    """

    hook: str | None = None
    caption: str | None = None
    first_comment: str | None = None
    overlay_text: str | None = None
    highlight_phrases: list[str] | None = None
    hashtags: list[str] | None = None
    image_prompt: str | None = None


@router.patch("/drafts/{draft_id}")
def update_draft(
    draft_id: int,
    edit: DraftEdit,
    session: Session = Depends(get_session),
) -> Draft:
    draft = _require(session, draft_id)
    for field, value in edit.model_dump(exclude_unset=True).items():
        setattr(draft, field, value)
    return _save(session, draft)


@router.post("/drafts/{draft_id}/approve")
def approve_draft(draft_id: int, session: Session = Depends(get_session)) -> Draft:
    """A failed run cannot be approved — there is nothing in it to approve.

    Rejecting one is still allowed: that is how it leaves the queue.
    """
    if _require(session, draft_id).status == DraftStatus.FAILED:
        raise HTTPException(
            status_code=409, detail="That draft failed and has nothing to approve."
        )
    return _set_status(session, draft_id, DraftStatus.APPROVED)


@router.post("/drafts/{draft_id}/unapprove")
def unapprove_draft(draft_id: int, session: Session = Depends(get_session)) -> Draft:
    """Nothing publishes in v1, so Approve is a queue movement, not a commitment.

    An approved Draft can come back, which is why nothing downstream may treat
    Approve as final.
    """
    return _set_status(session, draft_id, DraftStatus.REVIEW)


@router.post("/drafts/{draft_id}/reject")
def reject_draft(draft_id: int, session: Session = Depends(get_session)) -> Draft:
    return _set_status(session, draft_id, DraftStatus.REJECTED)


def _require(session: Session, draft_id: int) -> Draft:
    draft = session.get(Draft, draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail=f"No draft {draft_id}")
    if draft.status == DraftStatus.GENERATING:
        raise HTTPException(
            status_code=409, detail="That draft is still being written."
        )
    return draft


def _set_status(session: Session, draft_id: int, status: DraftStatus) -> Draft:
    draft = _require(session, draft_id)
    draft.status = status
    return _save(session, draft)


def _save(session: Session, draft: Draft) -> Draft:
    draft.updated_at = datetime.now(timezone.utc)
    session.add(draft)
    session.commit()
    session.refresh(draft)
    return draft
