"""Auto-drafts: top each Page's queue up from its unused competitor posts.

Requirements: the auto-drafts PRD.

A cron outside the app POSTs `/generate/auto`. There is no scheduler here and
no queue table - the Draft row is the job record, so a restart mid-run needs no
recovery code beyond `generate.sweep_stranded`.
"""

from datetime import timedelta

from sqlmodel import Session, col, func, select

from app import generate
from app.log import logger
from app.models import Draft, DraftStatus, Page, SourceItem
from app.routes.sources import _visible_to
from app.settings import sources as sources_config

WAITING = (DraftStatus.GENERATING, DraftStatus.REVIEW)
"""What counts against a Page's target.

`failed` is absent deliberately: counting it would stop a Page generating on
a day when something is broken. Counting `generating` is what makes the run
safe to call twice, which is why this module has no lock.
"""


def waiting(session: Session, page_id: int) -> int:
    """How many drafts this Page already has in the queue."""
    return session.exec(
        select(func.count(col(Draft.id)))
        .where(Draft.page_id == page_id)
        .where(col(Draft.status).in_(WAITING))
    ).one()


def pick(session: Session, page: Page, count: int) -> list[SourceItem]:
    """This Page's `count` highest-reaction competitor posts that nothing has used.

    Ranked flat by reactions, which is **not** how the Sources grid ranks -
    that partitions by author so every competitor is offered before any
    repeats. Decided 2026-09-20 with the measurement in the PRD.

    The window is anchored to the newest post in scope rather than to the
    clock, so a Page whose sync is a day behind still has candidates. Same
    reasoning as `routes/sources.py`.
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

    return list(
        session.exec(
            select(SourceItem)
            .where(*where)
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
    """Top this Page's queue up to `target`. Returns the new Draft ids.

    An empty return is an ordinary run: the queue was full, or the Page has
    nothing unused left in the window.
    """
    short = target - waiting(session, page.id)
    if short <= 0:
        return []

    items = pick(session, page, short)
    if not items:
        logger.bind(page=page.name).info(
            "No auto-draft for {}: nothing unused in the window", page.name
        )
        return []

    return generate.start_run(
        session,
        [page.id],
        list(items),
        hero_from_source=hero_from_source,
    )
