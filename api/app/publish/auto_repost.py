"""Automatic save and repost (H2): the Overview's two buttons, without the buttons.

The client: "once a post achieves 1000 likes the exact same post is rescheduled
for 30 days times... at first available slot." Per Page, from Settings:
`Page.auto_save_min_reactions` saves a post that crosses it, and
`Page.auto_repost_after_days` reposts it that many days after it first went out.
The requirements are web/content/PRDs/auto-repost.md; the design record is
the commit that added this file.

**The trigger is the operator opening the app.** Nothing pushes "a post passed N
reactions" (Metricool's webhooks and Facebook's Page feed webhook were both
checked), so `GET /pages`, which every screen calls, queues `run_pages` as a
background task. A repost is scheduled weeks ahead, so a check at whatever time
KC next opens the app costs nothing.

ponytail: in-process throttle and lock, correct only with `--workers 1`, which
the Dockerfile already pins. A Page nobody opens the app for in 30 days can miss
a crossing; a cron calling `run_pages` is the upgrade.

**This is the first path to an audience that skips Review**, agreed as such.
The repost is still visible and cancellable on Schedule weeks before it goes.
"""

import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.db import get_engine
from app.log import logger
from app.models import Draft, Page, PageTimeSlot, SavedPost
from app.publish import metricool as publisher
from app.publish import repost
from app.routes.drafts import schedule_draft
from app.routes.overview import _flatten
from app.routes.schedule import SLOT_SEARCH_DAYS, busy_minutes, free_slot
from app.settings import settings
from app.sources import metricool

STATS_DAYS = 30
"""The stats window read for threshold crossings. Metricool's own default and
the Overview's; a post older than this is never auto-saved."""

THROTTLE = timedelta(hours=6)
"""How long a checked Page is left alone. `GET /pages` fires on every load."""

REPOSTS_PER_RUN = 3
"""Reposts scheduled per Page per run, earliest target first.

With N under 30 days, most posts over the threshold are already past their
target the first time a run sees them. Uncapped, History Retraced's 26 would
take the next 26 free slots at once, and manual Publish, which offers the same
free slots through `next_slot`, would find nothing free for days."""

_checked: dict[int, datetime] = {}
"""When each Page was last queued for a run. Stamped before the run is queued,
so two tabs opening at once queue one."""

_run_lock = threading.Lock()


@dataclass
class Report:
    """What a run did, or with `dry_run` what it would have done."""

    saved: list[str] = field(default_factory=list)
    """Post ids saved."""

    scheduled: list[tuple[str, datetime]] = field(default_factory=list)
    """Post id, and the naive local time it was scheduled at."""

    not_scheduled: list[tuple[str, str]] = field(default_factory=list)
    """Post id, and why."""


def due(pages: list[Page]) -> list[int]:
    """The Pages with auto-save on that have not been checked lately, stamped."""
    now = datetime.now(timezone.utc)
    ids = [
        page.id
        for page in pages
        if page.id is not None
        and page.auto_save_min_reactions
        and now - _checked.get(page.id, datetime.min.replace(tzinfo=timezone.utc))
        > THROTTLE
    ]
    # Unlocked: two requests racing here both queue a run, and `_run_lock`
    # makes the second a no-op.
    for page_id in ids:
        _checked[page_id] = now
    return ids


def run_pages(page_ids: list[int]) -> None:
    """Run each Page, as a BackgroundTask. Never raises; one Page failing is
    logged and the others still run. A run already in progress wins."""
    if not _run_lock.acquire(blocking=False):
        return
    try:
        with Session(get_engine()) as session:
            for page_id in page_ids:
                page = session.get(Page, page_id)
                if page is None:
                    continue
                try:
                    report = run(session, page)
                except Exception:  # noqa: BLE001 - a BackgroundTask must not raise
                    session.rollback()
                    logger.exception("Auto repost failed for {}", page.name)
                    continue
                if report.saved or report.scheduled or report.not_scheduled:
                    logger.bind(page=page.name).info(
                        "Auto repost for {}: saved {}, scheduled {}, not scheduled {}",
                        page.name,
                        len(report.saved),
                        len(report.scheduled),
                        len(report.not_scheduled),
                    )
    except Exception:  # noqa: BLE001
        logger.exception("Auto repost failed for pages {}", page_ids)
    finally:
        _run_lock.release()


def run(session: Session, page: Page, dry_run: bool = False) -> Report:
    """Save what crossed the threshold, then schedule the reposts that are due.

    **Nothing happens in rehearsal** (`METRICOOL_PUBLISH_AS_DRAFT=true`, every
    laptop) unless it is a dry run. Rehearsal protects manual Publish and not
    this: opening the app locally would write planner drafts nobody asked for,
    and against a shared database it would record posts as reposted with only
    a rehearsal draft behind them, so production never schedules the real one.

    `dry_run` reads stats, the planner and the database and writes to none of
    them. It does not copy images, so a dead original shows up only as a
    missing planner row, not as an expired link.
    """
    report = Report()
    if settings.metricool_publish_as_draft and not dry_run:
        return report
    if not page.auto_save_min_reactions or not page.metricool_blog_id:
        return report

    new = _auto_save(session, page, dry_run, report)
    if page.auto_repost_after_days:
        _auto_repost(session, page, new if dry_run else [], dry_run, report)
    return report


def _auto_save(
    session: Session, page: Page, dry_run: bool, report: Report
) -> list[SavedPost]:
    threshold = page.auto_save_min_reactions or 0
    rows = metricool.page_posts(page.metricool_blog_id or "", STATS_DAYS)

    # Metricool's stats for Hot Tub Timeout's blog id return History Retraced's
    # posts, identical rows (measured 2026-09-15). Unguarded, this would save
    # them under the wrong Page and repost them onto the wrong Facebook Page.
    prefix = f"{page.facebook_page_id}_"
    ours = [row for row in rows if str(row.get("postId") or "").startswith(prefix)]
    if len(ours) < len(rows):
        logger.bind(page=page.name).warning(
            "Auto repost ignored {} stats row(s) for {} that belong to another Facebook Page",
            len(rows) - len(ours),
            page.name,
        )

    # Dismissed rows included in both: a dismissed post stays dismissed, and a
    # repost of it is still a repost.
    existing = session.exec(select(SavedPost).where(SavedPost.page_id == page.id)).all()
    known_ids = {row.metricool_post_id for row in existing}
    known_captions = {repost._match_key(row.text) for row in existing} - {""}

    new = []
    for row in ours:
        post = _flatten(row, set())
        key = repost._match_key(post.text)
        if post.reactions < threshold or post.post_id in known_ids:
            continue
        # A caption already saved is this post published before: a repost is
        # not reposted (Q3). Blank captions match nothing, not each other.
        if key and key in known_captions:
            continue
        known_ids.add(post.post_id)
        known_captions.add(key)

        saved = SavedPost(
            page_id=page.id or 0,
            metricool_post_id=post.post_id,
            text=post.text,
            permalink_url=post.permalink_url,
            picture_url=post.picture_url,
            published_at=(
                datetime.fromisoformat(post.published_at) if post.published_at else None
            ),
            reactions=post.reactions,
            comments=post.comments,
            shares=post.shares,
            impressions=post.impressions,
            note=f"Saved automatically at {post.reactions:,} reactions",
            auto_saved=True,
        )
        if not dry_run:
            session.add(saved)
            try:
                session.commit()
            except IntegrityError:
                # Saved by hand, or by another run, since the read above.
                session.rollback()
                continue
        new.append(saved)
        report.saved.append(post.post_id)
    return new


def target_for(row: SavedPost, days: int, start: datetime) -> datetime:
    """When this post is due again: published plus N days, in the Page's zone.

    `published_at` is UTC (stored naive by Postgres); slots and the planner are
    naive local. Adding N days to the UTC value puts the repost 7 hours off.
    Never earlier than `start`, which is the next whole minute.
    """
    if row.published_at is None:
        return start
    published = row.published_at
    if published.tzinfo is None:
        published = published.replace(tzinfo=timezone.utc)
    local = published.astimezone(ZoneInfo(settings.timezone)).replace(tzinfo=None)
    return max(local + timedelta(days=days), start)


def _auto_repost(
    session: Session,
    page: Page,
    unsaved: list[SavedPost],
    dry_run: bool,
    report: Report,
) -> None:
    days = page.auto_repost_after_days or 0
    candidates = list(
        session.exec(
            select(SavedPost)
            .where(SavedPost.page_id == page.id)
            .where(SavedPost.auto_saved == True)  # noqa: E712
            .where(SavedPost.repost_draft_id.is_(None))  # type: ignore[union-attr]
            .where(SavedPost.repost_error.is_(None))  # type: ignore[union-attr]
            .where(SavedPost.dismissed_at.is_(None))  # type: ignore[union-attr]
        ).all()
    ) + unsaved
    if not candidates:
        return

    slots = list(
        session.exec(
            select(PageTimeSlot)
            .where(PageTimeSlot.page_id == page.id)
            .order_by(PageTimeSlot.minute_of_day)  # type: ignore[arg-type]
        ).all()
    )
    if not slots:
        # A Page-wide problem, not a per-post one, so nothing is claimed and
        # the next run tries again once times are set.
        logger.bind(page=page.name).warning(
            "Auto repost skipped for {}: no publishing times configured", page.name
        )
        return

    now = datetime.now(ZoneInfo(settings.timezone)).replace(tzinfo=None)
    start = now.replace(second=0, microsecond=0) + timedelta(minutes=1)
    due_rows = sorted(
        ((target_for(row, days, start), row) for row in candidates),
        key=lambda pair: pair[0],
    )[:REPOSTS_PER_RUN]

    # One planner read covers every target: up to 90 days out plus the search.
    latest = due_rows[-1][0] + timedelta(days=SLOT_SEARCH_DAYS)
    blog_id = page.metricool_blog_id or ""
    try:
        busy = busy_minutes(publisher.list_scheduled(blog_id, now, latest))
    except publisher.PublishError as error:
        logger.bind(page=page.name).warning(
            "Auto repost skipped for {}: {}", page.name, error
        )
        return

    for target, row in due_rows:
        if dry_run:
            found = free_slot(slots, busy, target)
            if not (repost.original_for(page, row) or {}).get("media"):
                report.not_scheduled.append((row.metricool_post_id, "no original in the planner"))
            elif found is None:
                report.not_scheduled.append((row.metricool_post_id, "no free slot"))
            else:
                busy.add(found[0])
                report.scheduled.append((row.metricool_post_id, found[0]))
            continue

        try:
            draft = repost.draft_from_saved(session, page, row)
        except repost.RepostError as error:
            if error.status == 409:
                row.repost_error = str(error)
                session.add(row)
                session.commit()
            # A 502 leaves the row untouched, so the next run retries.
            report.not_scheduled.append((row.metricool_post_id, str(error)))
            continue

        # The claim, committed with the Draft and before Metricool is called.
        # Killed after this, the post is a Draft at `review` with no Metricool
        # id: not reposted, but visible and publishable by hand. Claiming after
        # scheduling would risk the worse failure, the post going out twice.
        row.repost_draft_id = draft.id
        session.add(row)
        session.commit()

        found = free_slot(slots, busy, target)
        if found is None:
            _unscheduled(
                session,
                draft,
                f"Not scheduled automatically: every publishing time for "
                f"{SLOT_SEARCH_DAYS} days from {target:%d %b} already has a post.",
            )
            report.not_scheduled.append((row.metricool_post_id, "no free slot"))
            continue

        when = found[0]
        busy.add(when)
        try:
            draft.metricool_post_id = schedule_draft(draft, blog_id, when)
        except publisher.PublishError as error:
            _unscheduled(session, draft, f"Not scheduled automatically: {error}")
            report.not_scheduled.append((row.metricool_post_id, str(error)))
            continue

        draft.updated_at = datetime.now(timezone.utc)
        session.add(draft)
        session.commit()
        logger.bind(
            page=page.name, draft_id=draft.id, metricool_post_id=draft.metricool_post_id
        ).info(
            "Auto reposted {} as draft {} for {}", row.metricool_post_id, draft.id, when
        )
        report.scheduled.append((row.metricool_post_id, when))


def _unscheduled(session: Session, draft: Draft, warning: str) -> None:
    """Leave the repost at `review` saying why: today's manual Repost, not a
    retry loop."""
    draft.warnings = [*draft.warnings, warning]
    session.add(draft)
    session.commit()
