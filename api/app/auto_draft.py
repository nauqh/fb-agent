"""Auto-drafts: write each Page a few drafts from its unused competitor posts.

Requirements: the auto-drafts PRD.

A cron outside the app POSTs `/generate/auto`. There is no scheduler here and
no queue table - the Draft row is the job record, so a restart mid-run needs no
recovery code beyond `generate.sweep_stranded`.
"""

from datetime import timedelta

from sqlmodel import Session, col, func, select

from app import generate
from app.log import logger
from app.models import AutoDraftRun, Draft, Page, SourceItem
from app.routes.sources import _visible_to
from app.settings import sources as sources_config


def _candidates(session: Session, page: Page) -> list:
    """The filters a post must pass to be written about for this Page.

    Shared so that counting what is left and taking from it cannot drift - a
    "running dry" warning derived from a different rule than the run itself
    would be worse than no warning.

    - **Assigned.** `_visible_to` is the Sources grid's rule: a post reaches a
      Page because someone ticked that competitor for it.
    - **Unused**, by any Draft for any Page. Ten Pages share one competitor
      pool, so per-Page would write the same story once per Page.
    - **Inside the window**, anchored to the newest post in scope rather than
      the clock, so a Page whose sync is a day behind still has candidates.
    """
    visible = _visible_to(session, [page.id])

    spent = select(col(Draft.source_item_id)).where(
        col(Draft.source_item_id).is_not(None)
    )
    where = [visible, col(SourceItem.id).not_in(spent)]

    newest_at = session.exec(
        select(func.max(col(SourceItem.published_at))).where(visible)
    ).one()
    if newest_at is not None:
        window = newest_at - timedelta(days=sources_config.competitors.lookback_days)
        where.append(col(SourceItem.published_at) >= window)

    return where


def available(session: Session, page: Page) -> int:
    """How many posts this Page could still be written about. Zero is running dry."""
    return session.exec(
        select(func.count(col(SourceItem.id))).where(*_candidates(session, page))
    ).one()


def pick(session: Session, page: Page, count: int) -> list[SourceItem]:
    """This Page's `count` highest-reaction candidates.

    Ranked flat by reactions, which is **not** how the Sources grid ranks -
    that partitions by author so every competitor is offered before any
    repeats. Decided 2026-09-20 with the measurement in the PRD.
    """
    return list(
        session.exec(
            select(SourceItem)
            .where(*_candidates(session, page))
            .order_by(
                col(SourceItem.reactions).desc().nulls_last(),
                col(SourceItem.published_at).desc(),
            )
            .limit(count)
        ).all()
    )


def run(
    session: Session,
    page: Page,
    target: int,
    hero_from_source: bool = False,
) -> list[int]:
    """Generate `target` drafts for this Page. Returns the new Draft ids.

    A flat count, not a top-up. Drafts already in `review` are not a queue
    here: measured 2026-09-21, the seven Pages with competitors assigned held
    9 to 247 of them, the oldest 41 days, so a run that subtracted them would
    never generate anything again.

    Nothing stops two runs an hour apart producing two more drafts each. What
    they cannot do is produce the *same* draft twice - `_candidates` excludes
    every post a draft already came from.

    **A run is recorded whether or not it produced anything**, which is the
    whole point of the row: a night the cron did not fire and a night it found
    nothing look identical in the Draft table and different here.
    """
    items = pick(session, page, target)
    draft_ids: list[int] = []
    note = None

    if not items:
        note = "No unused competitor posts left in the window"
        logger.bind(page=page.name).info("No auto-draft for {}: {}", page.name, note)
    else:
        draft_ids = generate.start_run(
            session,
            [page.id],
            list(items),
            hero_from_source=hero_from_source,
        )
        if len(items) < target:
            note = f"Only {len(items)} post(s) left to write about, asked for {target}"

    session.add(
        AutoDraftRun(
            page_id=page.id,
            drafts_created=len(draft_ids),
            available=available(session, page),
            note=note,
        )
    )
    session.commit()

    return draft_ids
