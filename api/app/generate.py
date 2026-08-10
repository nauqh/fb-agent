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

from app import media
from app.db import get_engine
from app.image import compositor, hero
from app.image import text as overlay
from app.models import Draft, DraftStatus, Page, SourceItem, SourceItemBase, SourceKind
from app.settings import settings
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
    # Read once for the whole cart, not once per item. A cart is routinely a
    # dozen ticks and this is a query now that feeds are rows rather than a
    # frozen object built at import.
    hosts = rss.curated_hosts(session)

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
        if item.kind == SourceKind.RSS and not rss.is_curated_url(item.url, hosts):
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

        _progress(session, draft, "writing the post", 20)
        result = writer.write(page, source, draft.topic)
        content = result.output

        draft.hook = content.hook
        draft.caption = content.caption
        draft.first_comment = content.first_comment
        draft.highlight_phrases = content.highlight_phrases
        draft.hashtags = content.hashtags
        draft.image_prompt = content.image_prompt

        # Residue: what the writer could not fix within its retries. Every
        # blocking rule is enforced first, so a Warning from `check` has already
        # survived correction. `advise` adds the rules that were never enforced
        # because they cannot be satisfied on demand.
        draft.warnings = validators.check(
            content.hook, content.caption, content.first_comment
        )
        draft.warnings += validators.advise(content.first_comment)
        draft.warnings += _highlight_warnings(content)

        # Deliberately still `generating`. Setting `review` here — before the
        # hero exists — put a finished-looking row in the queue with a blank
        # thumbnail, and stopped the client polling, because it polls only while
        # something is `generating`. The picture then landed twenty seconds
        # later with nothing left to fetch it, so it never appeared until the
        # operator reloaded. A draft is not in review until it is whole.
        _progress(session, draft, "drawing the image", 60)

        # Rebound, never `+=`. `warnings` is a plain JSON column with no
        # mutation tracking, so an in-place append after the last commit is
        # invisible to SQLAlchemy and never reaches the row.
        draft.warnings = draft.warnings + build_image(session, draft, page)

        # Cleared on success, or a row the startup sweep marked while this task
        # was still running keeps "Interrupted by a restart" forever and the
        # queue renders a finished draft as failed.
        draft.error = None
        draft.status = DraftStatus.REVIEW
        _progress(session, draft, "done", 100)

    except Exception as error:  # noqa: BLE001 — the row is where a failure goes
        draft.error = f"{type(error).__name__}: {error}"[:500]
        draft.status = DraftStatus.FAILED
        draft.progress_step = "failed"
        draft.progress_pct = 100
        draft.updated_at = datetime.now(timezone.utc)
        session.add(draft)
        session.commit()


IMAGE_WARNING = "Image: "
"""Prefix on every warning this step produces, so a rebuild can replace them.

Without a marker there is no way to tell a stale image warning from a live
brand-rule one, and re-compositing appends a second copy of a complaint the
operator has just fixed.
"""


def build_image(session: Session, draft: Draft, page: Page) -> list[str]:
    """Hero, then composite, then store. Returns warnings; never raises.

    **A picture that fails must not throw away text that worked.** The draft
    stays at `review` with its copy intact and the reason in `warnings`, because
    the alternative is a `failed` row whose caption was fine and whose only
    problem was one refused prompt. That is also why this is a separate entry
    point: `POST /drafts/{id}/image` calls it again without re-billing the
    writer.

    The paths are stored separately on purpose. Re-compositing after an overlay
    edit reuses `hero_image_path`, so editing the text is free and only a
    genuinely new picture is charged for. `inset_image_path` is free either way
    — it is an upload, not a generation.
    """
    if not draft.hook:
        return [f"{IMAGE_WARNING}no hook, so there is nothing to draw."]

    try:
        plan = overlay.plan(draft.hook)
        warnings: list[str] = []

        if draft.hero_image_path:
            image_bytes = media.store.read(draft.hero_image_path)
        else:
            drawn = hero.generate(draft.image_prompt or "", plan.hero_height_px)
            image_bytes = drawn.data
            if drawn.model != settings.gemini_image_model:
                # A backup model draws in a different style, and the operator is
                # the only one who can judge whether this one is off-brand. A
                # text fallback needs no such notice; a picture does.
                warnings.append(
                    f"{IMAGE_WARNING}drawn by {drawn.model}, not "
                    f"{settings.gemini_image_model}, which was unavailable. "
                    "Check it looks right, or rebuild later."
                )
            draft.hero_image_path = media.store.save(
                image_bytes, media.filename(draft.id or 0, "hero", "png")
            )

        composed = compositor.compose(
            image_bytes,
            plan,
            draft.highlight_phrases,
            page.watermark_image_path,
            _inset(draft),
        )
        superseded = draft.composed_image_path
        draft.composed_image_path = media.store.save(
            composed, media.filename(draft.id or 0, "composed", "jpg")
        )
        session.add(draft)
        session.commit()

        # Only after the row points at the new file. The other order — delete,
        # then save — turns a failed upload into a draft with no picture at all.
        # This way the worst case is one file nobody reads.
        if superseded and superseded != draft.composed_image_path:
            _discard(superseded)

        return warnings

    except Exception as error:  # noqa: BLE001 — a warning, not a dead draft
        return [f"{IMAGE_WARNING}{type(error).__name__}: {error}"[:300]]


def _discard(stored: str) -> None:
    """Drop one composite this rebuild replaced. The exact path, never a pattern.

    Every overlay edit and every slider nudge writes a new composite and orphans
    the last one, which is how seven drafts became 37MB with nothing ever
    deleted. The bucket's free tier is 1GB and dev shares it, so unbounded is not
    an option the way it was on a laptop disk.

    Safe to do at all only because a published draft cannot rebuild
    (`routes/drafts._editable`): Metricool holds a link to the composite and
    Facebook has not fetched it yet.

    The path comes from the row and is used verbatim. No prefix, no pattern — a
    `ls | grep | rm` in this repo once swept up an image the operator had
    uploaded, and object storage has no undo.

    Failure here is deliberately silent. The row is already correct and already
    committed; reporting a failed cleanup as an image warning would say the
    picture is broken when it is fine. The cost of the silence is one orphan.
    """
    try:
        media.store.delete(stored)
    except Exception:  # noqa: BLE001 — a leaked file, not a broken draft
        pass


def _inset(draft: Draft) -> compositor.Inset | None:
    """The uploaded circle, if there is one. Nothing generates this.

    A file the operator chose, so a run never waits on it and never pays for
    it: a fresh draft has no inset, and one appears when somebody uploads it.
    """
    if not draft.inset_image_path:
        return None
    return compositor.Inset(
        media.store.read(draft.inset_image_path),
        draft.inset_size_px,
        draft.inset_x_ratio,
        draft.inset_y_ratio,
    )


def _highlight_warnings(content) -> list[str]:
    """Highlighting is a substring match, so a phrase off by one renders no gold.

    Caught here rather than in `validators.check` because it is a rule about the
    *compositor*, not about the brand — see design.md on `overlay.txt` being a
    contract with the renderer.
    """
    missing = [p for p in content.highlight_phrases if p not in content.hook]
    if missing:
        return [
            f"{len(missing)} highlight phrase(s) are not verbatim in the hook "
            f"and will render no gold: {missing[:3]}"
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
        draft.status = DraftStatus.FAILED
        draft.progress_step = "failed"
        draft.progress_pct = 100
        session.add(draft)
    session.commit()
    return len(stranded)
