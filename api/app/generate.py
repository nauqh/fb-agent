"""The run: rows in, drafts out.

What replaced a six-node LangGraph. `resolvePrompt` is a Page read, `loadPosts`
is a Source Item read, `summarize` is deleted (it mapped each post to itself
without calling a model), `validateAll` moved inside the writer, and `saveBatch`
is a transaction. What is left is this file.

**This is the only thing that writes a Source Item.** Browsing does not write —
the Cart carries items, and they become rows here, when something actually uses
them. See docs/plan.md, "Ticking stops writing".
"""

from datetime import datetime, timezone

from sqlmodel import Session, select

from app.db import get_engine
from app.models import Draft, DraftStatus, Page, SourceItem, SourceItemBase, SourceKind
from app.sources import rss
from app.writer import agent as writer
from app.writer import validators


class GenerateError(ValueError):
    """A request that cannot be run. Raised before anything is written."""


def resolve_sources(
    session: Session, items: list[SourceItemBase]
) -> list[SourceItem]:
    """Turn what the client sent into rows, creating only what it may create.

    A body is accepted only for a kind the client is allowed to author:

    - **RSS** by value, host-checked against the curated feeds. The tab is live,
      so there is no server-side copy to compare against; without the check this
      accepts arbitrary text and hands it to the writer.
    - **Tweet** by value. The same trust level as RSS but with no host allowlist
      to check — a tweet id is not a domain. Re-reading it would double a paid
      X call for a body we just showed the operator.
    - **Competitor post** by reference only. The Metricool sync owns those rows,
      and there is no equivalent of `is_curated_url` for a Facebook post, so a
      body that does not already exist as a row is refused rather than trusted.
    """
    resolved: list[SourceItem] = []

    for item in items:
        if not item.external_id:
            raise GenerateError("A source item needs an external_id")

        existing = session.exec(
            select(SourceItem)
            .where(SourceItem.kind == item.kind)
            .where(SourceItem.external_id == item.external_id)
        ).first()

        if existing is not None:
            resolved.append(existing)
            continue

        if item.kind == SourceKind.COMPETITOR_POST:
            raise GenerateError(
                f"Unknown competitor post {item.external_id!r}. Sync the "
                f"Competitors tab first — the sync owns those rows."
            )
        if item.kind == SourceKind.RSS and not rss.is_curated_url(item.url):
            raise GenerateError(f"Not from a curated feed: {item.url}")

        row = SourceItem(**item.model_dump())
        session.add(row)
        resolved.append(row)

    return resolved


def start_run(
    session: Session,
    page_ids: list[int],
    sources: list[SourceItemBase],
    topic: str | None = None,
) -> list[int]:
    """Insert one placeholder Draft per (source × page) and return the ids.

    Returns immediately. The row *is* the job record — that is why `Draft`
    carries progress columns and why there is no queue and no event table.
    """
    if not page_ids:
        raise GenerateError("A run needs at least one page")
    if not sources and not topic:
        raise GenerateError("A run needs either source items or a topic")

    pages = session.exec(select(Page).where(Page.id.in_(page_ids))).all()  # type: ignore[union-attr]
    missing = set(page_ids) - {page.id for page in pages}
    if missing:
        raise GenerateError(f"No page {sorted(missing)[0]}")

    rows = resolve_sources(session, sources)
    session.flush()  # so every SourceItem has an id to point a Draft at

    drafts = [
        Draft(
            page_id=page_id,
            source_item_id=row.id if row else None,
            topic=topic if row is None else None,
            status=DraftStatus.GENERATING,
            progress_step="queued",
            progress_pct=0,
        )
        for page_id in page_ids
        for row in (rows or [None])
    ]
    for draft in drafts:
        session.add(draft)
    session.commit()

    return [draft.id for draft in drafts if draft.id is not None]


def run_drafts(draft_ids: list[int]) -> None:
    """Fill the placeholder rows in. Runs as a BackgroundTask, off the request.

    Its own session: FastAPI runs background work on a different thread to the
    request that spawned it, and this outlives that request by minutes.

    Never raises. A failure belongs on the row, where the operator can see it —
    an exception here would land in a log nobody reads while the Draft sat at
    `generating` forever.
    """
    with Session(get_engine()) as session:
        for draft_id in draft_ids:
            _run_one(session, draft_id)


def _run_one(session: Session, draft_id: int) -> None:
    draft = session.get(Draft, draft_id)
    if draft is None:
        return

    try:
        page = session.get(Page, draft.page_id)
        assert page is not None
        source = (
            session.get(SourceItem, draft.source_item_id)
            if draft.source_item_id
            else None
        )

        _progress(session, draft, "writing", 20)
        result = writer.write(page, source, draft.topic)
        content = result.output

        draft.hook = content.hook
        draft.caption = content.caption
        draft.first_comment = content.first_comment
        draft.overlay_text = content.overlay_text
        draft.highlight_phrases = content.highlight_phrases
        draft.hashtags = content.hashtags
        draft.image_prompt = content.image_prompt

        # Residue: what the writer could not fix within its retries. Every rule
        # is enforced first, so a Warning here has already survived correction.
        draft.warnings = validators.check(
            content.hook, content.caption, content.first_comment
        )
        draft.warnings += _highlight_warnings(content)

        draft.status = DraftStatus.REVIEW
        _progress(session, draft, "done", 100)

    except Exception as error:  # noqa: BLE001 — the row is where a failure goes
        draft.error = f"{type(error).__name__}: {error}"[:500]
        draft.status = DraftStatus.REVIEW
        draft.progress_step = "failed"
        draft.progress_pct = 100
        draft.updated_at = datetime.now(timezone.utc)
        session.add(draft)
        session.commit()


def _highlight_warnings(content) -> list[str]:
    """Highlighting is a substring match, so a phrase off by one renders no gold.

    Caught here rather than in `validators.check` because it is a rule about the
    *compositor*, not about the brand — see design.md on `overlay.txt` being a
    contract with the renderer.
    """
    missing = [p for p in content.highlight_phrases if p not in content.overlay_text]
    if missing:
        return [
            f"{len(missing)} highlight phrase(s) are not verbatim in the overlay "
            f"text and will render no gold: {missing[:3]}"
        ]
    return []


def _progress(session: Session, draft: Draft, step: str, pct: int) -> None:
    draft.progress_step = step
    draft.progress_pct = pct
    draft.updated_at = datetime.now(timezone.utc)
    session.add(draft)
    session.commit()


def sweep_stranded(session: Session) -> int:
    """Mark rows left at `generating` by a restart as failed.

    Safe only because there is exactly one writer process: with one, nothing
    else could still own the row. Two processes and this would kill live runs.
    """
    stranded = session.exec(
        select(Draft).where(Draft.status == DraftStatus.GENERATING)
    ).all()
    for draft in stranded:
        draft.error = "Interrupted by a restart before it finished."
        draft.status = DraftStatus.REVIEW
        draft.progress_step = "failed"
        draft.progress_pct = 100
        session.add(draft)
    session.commit()
    return len(stranded)
