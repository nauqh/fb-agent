"""Auto-drafts: write each Page a few drafts from its unused sources.

Requirements: the auto-drafts PRD. Two sources, each switched on per Page from
Settings: competitor posts (`run`) and the Page's RSS feeds (`run_rss`).

A cron outside the app POSTs `/generate/auto`. There is no scheduler here and
no queue table - the Draft row is the job record, so a restart mid-run needs no
recovery code beyond `generate.sweep_stranded`.
"""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field
from sqlmodel import Session, col, func, select

from app import generate
from app.log import logger
from app.models import (
    AutoDraftRun,
    Draft,
    Page,
    Shortlist,
    SourceItem,
    SourceItemBase,
    SourceKind,
)
from app.routes.sources import _feeds_for, _visible_to
from app.settings import settings
from app.settings import sources as sources_config
from app.sources import rss
from app.writer import agent as writer


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
    - **Loud enough**, when the Page sets a reaction floor.
    """
    visible = _visible_to(session, [page.id])

    where = [visible, col(SourceItem.id).not_in(_spent())]
    if page.auto_draft_competitor_min_reactions:
        where.append(
            col(SourceItem.reactions) >= page.auto_draft_competitor_min_reactions
        )

    newest_at = session.exec(
        select(func.max(col(SourceItem.published_at))).where(visible)
    ).one()
    if newest_at is not None:
        window = newest_at - timedelta(days=sources_config.competitors.lookback_days)
        where.append(col(SourceItem.published_at) >= window)

    return where


def _spent():
    """Every Source Item a Draft already came from, for any Page."""
    return select(col(Draft.source_item_id)).where(col(Draft.source_item_id).is_not(None))


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
            **_pictures(page.auto_draft_competitor_picture, hero_from_source),
        )
        if len(items) < target:
            note = f"Only {len(items)} post(s) left to write about, asked for {target}"

    _record(session, page, SourceKind.COMPETITOR_POST, draft_ids, available(session, page), note)
    return draft_ids


def _pictures(choice: str, hero_from_source: bool) -> dict:
    """A Page's picture choice for one source, as `start_run` arguments.

    `hero_from_source` is the cron's own flag, kept so its `HERO_FROM_SOURCE`
    still works; the Page's choice wins wherever it says something else."""
    return {
        "no_image": choice == "none",
        "hero_from_source": choice == "source" or (hero_from_source and choice == "generate"),
        "hero_search": choice == "google",
    }


def _record(
    session: Session,
    page: Page,
    source: SourceKind,
    draft_ids: list[int],
    left: int,
    note: str | None,
) -> None:
    record = AutoDraftRun(
        page_id=page.id,
        source=source,
        drafts_created=len(draft_ids),
        available=left,
        note=note,
    )
    session.add(record)
    session.flush()
    for draft_id in draft_ids:
        session.get_one(Draft, draft_id).auto_draft_run_id = record.id
    session.commit()


# --- RSS -----------------------------------------------------------------------

RSS_POOL = 100
"""How many of the newest unused items the model is shown.

ponytail: a flat cap, so only a Page's newest 100 unused items are considered.
Raise it if a Page's criteria are narrow enough to miss what is further down."""

CHOOSE_INSTRUCTIONS = """\
You choose which news items a Facebook Page should write posts about.

You are given the Page's criteria and a numbered list of items, each a headline
and sometimes a summary. Return the numbers of every item that fits the
criteria, best fit first. Leave out anything the criteria exclude, and anything
you are unsure fits. An empty list is the right answer when nothing fits.
"""


class _Choice(BaseModel):
    picks: list[int] = Field(description="Item numbers that fit, best first.")


def rss_candidates(session: Session, page: Page) -> tuple[list[SourceItemBase], int]:
    """This Page's unused feed items, newest first, and how many feeds failed.

    Live, like the RSS tab: a feed item is not a row until a run uses it, so
    "unused" means no Draft has come from that link yet, for any Page.
    """
    fetched = rss.fetch_rss(_feeds_for(session, page))
    spent = set(
        session.exec(
            select(SourceItem.external_id).where(
                SourceItem.kind == SourceKind.RSS, col(SourceItem.id).in_(_spent())
            )
        ).all()
    )
    unused = [item for item in fetched.items if item.external_id not in spent]
    return unused, len(fetched.failures)


def choose(page: Page, items: list[SourceItemBase]) -> list[SourceItemBase]:
    """The items that fit the Page's instructions, best first. All of them when none are set."""
    criteria = (page.auto_draft_rss_instructions or "").strip()
    if not criteria or not items:
        return items

    shown = items[:RSS_POOL]
    listing = "\n".join(
        f"{number}. {item.text[:300].replace(chr(10), ' ')}"
        for number, item in enumerate(shown, start=1)
    )
    answer = writer.ask(
        f"CRITERIA:\n{criteria}\n\nITEMS:\n{listing}", _Choice, CHOOSE_INSTRUCTIONS
    ).output
    picks = [n for n in dict.fromkeys(answer.picks) if 1 <= n <= len(shown)]
    return [shown[n - 1] for n in picks]


def run_rss(
    session: Session,
    page: Page,
    target: int,
    hero_from_source: bool = False,
) -> list[int]:
    """Generate up to `target` drafts from this Page's feeds. Recorded like `run`.

    `available` on the row is how many more items fit, as at this run. The
    monitor shows that rather than re-reading every feed and asking the model
    again on each page load.

    A fetch or model failure is written onto the run row rather than raised: one
    Page's broken feed must not stop the Pages after it in the same cron.
    """
    draft_ids: list[int] = []
    notes: list[str] = []
    left = 0

    try:
        unused, failed = rss_candidates(session, page)
        if failed:
            notes.append(f"{failed} feed(s) did not answer")
        fitting = choose(page, unused)
        items = fitting[:target]
        left = len(fitting) - len(items)

        if not items:
            notes.insert(0, "No unused feed items fit" if unused else "No unused feed items left")
        else:
            draft_ids = generate.start_run(
                session,
                [page.id],
                list(items),
                **_pictures(page.auto_draft_rss_picture, hero_from_source),
            )
            if len(items) < target:
                notes.insert(0, f"Only {len(items)} item(s) fit, asked for {target}")
    except Exception as error:  # noqa: BLE001 - recorded on the run instead
        session.rollback()
        notes = [f"Could not choose from the feeds: {error}"]
        logger.bind(page=page.name).exception("RSS auto-draft failed for {}", page.name)

    note = "; ".join(notes) or None
    if note:
        logger.bind(page=page.name).info("RSS auto-draft for {}: {}", page.name, note)
    _record(session, page, SourceKind.RSS, draft_ids, left, note)
    return draft_ids


# --- Shortlist -----------------------------------------------------------------

COVERED_DAYS = 2
"""How far back a draft's story counts as covered, for the shortlist."""

SHORTLIST_INSTRUCTIONS = """\
You shortlist what a Facebook Page should post about next.

You are given the Page's criteria, the stories it has covered recently, and a
numbered list of candidates: news stories, and posts from other Facebook Pages
with their reaction counts. Return the numbers of the best fits, best first,
at most {size}. Leave out anything the criteria exclude, anything about the
same story as a recently covered one, and all but the best candidate on any
one story. An empty list is the right answer when nothing fits.
"""


def _covered(session: Session, page: Page) -> list[str]:
    """Headlines of the stories this Page drafted lately, from any outlet."""
    since = datetime.now(timezone.utc) - timedelta(days=COVERED_DAYS)
    texts = session.exec(
        select(SourceItem.text)
        .join(Draft, col(Draft.source_item_id) == col(SourceItem.id))
        .where(Draft.page_id == page.id, col(Draft.created_at) >= since)
        .distinct()
    ).all()
    return [(text or "").split("\n")[0][:200] for text in texts if text]


def shortlist(session: Session, page: Page) -> Shortlist:
    """The Page's `shortlist_size` best-fit unused sources, best first. Unsaved.

    Competitor posts and RSS items in one list, judged by the Page's
    instructions: the operator picks from ten rather than scrolling hundreds
    (client, 2026-10-28). Each pool is cut to `RSS_POOL` - the newest feed
    items, the loudest competitor posts - so one call sees both.

    Raises:
        ValueError: the Page has no instructions to judge by.
    """
    criteria = (page.auto_draft_rss_instructions or "").strip()
    if not criteria:
        raise ValueError("Write which stories fit this Page in Settings first.")

    news, failed = rss_candidates(session, page)
    posts = [SourceItemBase.model_validate(row.model_dump()) for row in pick(session, page, RSS_POOL)]
    pool = news[:RSS_POOL] + posts

    def line(number: int, item: SourceItemBase) -> str:
        label = (
            f"post, {item.reactions or 0} reactions"
            if item.kind is SourceKind.COMPETITOR_POST
            else "news"
        )
        return f"{number}. [{label}] {item.text[:300].replace(chr(10), ' ')}"

    covered = "\n".join(f"- {headline}" for headline in _covered(session, page)) or "(none)"
    listing = "\n".join(line(number, item) for number, item in enumerate(pool, start=1))
    picks: list[int] = []
    if pool:
        answer = writer.ask(
            f"CRITERIA:\n{criteria}\n\nCOVERED RECENTLY:\n{covered}\n\nCANDIDATES:\n{listing}",
            _Choice,
            SHORTLIST_INSTRUCTIONS.format(size=page.shortlist_size),
        ).output
        picks = [n for n in dict.fromkeys(answer.picks) if 1 <= n <= len(pool)]

    return Shortlist(
        page_id=page.id,
        items=[pool[n - 1].model_dump(mode="json") for n in picks[: page.shortlist_size]],
        considered=len(pool),
        failed_feeds=failed,
    )


def save_shortlist(session: Session, page: Page) -> Shortlist:
    """Make this Page's shortlist and store it over the last one. Commits."""
    fresh = shortlist(session, page)
    stored = session.merge(fresh)
    session.commit()
    session.refresh(stored)
    return stored


def shortlist_due(page: Page, made_at: datetime | None, now: datetime) -> bool:
    """Whether the Page's daily time has passed since its list was made.

    The latest occurrence of `shortlist_minute` at or before `now`, in the
    Page's zone; due if the list predates it. A late or missed hourly run is
    caught by the next one, or by the tab being opened.
    """
    if page.shortlist_minute is None:
        return False
    if made_at is None:
        return True
    zone = ZoneInfo(settings.timezone)
    local = now.astimezone(zone)
    hour, minute = divmod(page.shortlist_minute, 60)
    latest = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if latest > local:
        latest -= timedelta(days=1)
    # Stored naive, as UTC.
    return made_at.replace(tzinfo=made_at.tzinfo or timezone.utc) < latest


def due_shortlists(session: Session) -> list[int]:
    """The Pages whose shortlist is due and that have instructions to judge by."""
    now = datetime.now(timezone.utc)
    due: list[int] = []
    for page in session.exec(select(Page).order_by(col(Page.id))).all():
        if not (page.auto_draft_rss_instructions or "").strip():
            continue
        stored = session.get(Shortlist, page.id)
        if shortlist_due(page, stored.made_at if stored else None, now):
            due.append(page.id)
    return due


def make_shortlists(page_ids: list[int]) -> None:
    """Make each Page's shortlist, as a BackgroundTask. One Page failing is
    logged and the rest still run."""
    from app.db import get_engine

    with Session(get_engine()) as session:
        for page_id in page_ids:
            page = session.get(Page, page_id)
            if page is None:
                continue
            try:
                save_shortlist(session, page)
            except Exception:  # noqa: BLE001 - one Page must not stop the rest
                session.rollback()
                logger.bind(page=page.name).exception("Shortlist failed for {}", page.name)


def is_on(page: Page) -> bool:
    return bool(page.auto_draft_competitor_count or page.auto_draft_rss_count)


def run_page(session: Session, page: Page, hero_from_source: bool = False) -> list[int]:
    """Every source switched on for this Page, at its own count."""
    draft_ids: list[int] = []
    if page.auto_draft_competitor_count:
        draft_ids += run(session, page, page.auto_draft_competitor_count, hero_from_source)
    if page.auto_draft_rss_count:
        draft_ids += run_rss(session, page, page.auto_draft_rss_count, hero_from_source)
    return draft_ids
