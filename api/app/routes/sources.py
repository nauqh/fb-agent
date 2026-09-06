"""Sources: browse three kinds. Reads only.

**Browsing does not write.** Nothing here creates a Source Item — the Cart
carries what the operator ticked and `POST /generate` writes only what a run
uses, so an item that is browsed and abandoned leaves nothing behind.

Competitor posts are the standing exception, and stay one: the Metricool sync
writes them on arrival, because they are synced rather than browsed. Storage is
also what makes them checkable — there is no `is_curated_url` equivalent for a
Facebook post, so `POST /generate` takes a competitor by id and resolves it
against a row the sync owns. Phase 3 planned to drop the storage and re-fetch at
generate instead; that was reversed, because it would put a vendor call that has
already 502'd twice at the front of a 60-second run. See docs/plan.md, "But
competitor posts stay stored".
"""

from datetime import timedelta
from enum import Enum

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session, col, func, select

from app.db import get_session
from app.models import (
    Draft,
    Feed,
    Page,
    PageCompetitor,
    SourceItem,
    SourceItemBase,
    SourceKind,
)
from app.settings import sources as sources_config
from app.sources import metricool, rss, x

router = APIRouter(prefix="/sources", tags=["sources"])


class StoredSourceItem(SourceItemBase):
    """A stored Source Item, plus whether a Draft has already used it.

    `used` is derived per request rather than stored: a stored copy is a second
    truth, and when it drifts the grid quietly offers the operator a post they
    already published.
    """

    id: int
    used: bool = False


class FeedFailureOut(BaseModel):
    feed_url: str
    error: str


class RssFeedOut(BaseModel):
    """Items and failures together.

    The failures are part of the response, not a log line: a feed that rots is
    invisible off-screen, and the grid getting quieter looks exactly like a slow
    news week.
    """

    items: list[SourceItemBase]
    failures: list[FeedFailureOut]


def _scope(session: Session, page_ids: list[int] | None) -> list[Page]:
    """The Pages a competitor read covers. No ids means **every** Page.

    Competitor posts are a shared pool, and this is the function that makes them
    one. The constraint is Metricool's: a Metricool account may configure at
    most **100 competitors in total**, not per page. Five Pages that should each
    watch the same twenty sources would need those twenty added five times — one
    hundred, the whole allowance, for twenty distinct sources.

    So a source is added to one Page's competitor set in Metricool and read by
    all of them. `synced_for_page_id` stays on the row, but as *provenance* —
    which Page's set it arrived through — rather than as ownership.

    What this narrows is the **read**: the Pages whose tick lists `_visible_to`
    unions. It no longer narrows the sync, which always covers every brand —
    provenance is where the allowance had room, and a Page's freshness must not
    depend on it. See `get_competitor_posts`.

    Deliberately unlike RSS, which stays per-Page: feeds cost nothing to list
    twice, and the beats genuinely do not overlap.
    """
    if not page_ids:
        return list(session.exec(select(Page).order_by(Page.name)).all())  # type: ignore[arg-type]

    pages = []
    for page_id in dict.fromkeys(page_ids):
        page = session.get(Page, page_id)
        if page is None:
            raise HTTPException(status_code=404, detail=f"No page {page_id}")
        pages.append(page)
    return pages


def _assigned_to(session: Session, scope_ids: list[int]) -> list[str]:
    """The competitors these Pages are assigned, by Metricool `providerId`."""
    return list(
        session.exec(
            select(PageCompetitor.competitor_page_id)  # type: ignore[arg-type]
            .where(PageCompetitor.page_id.in_(scope_ids))  # type: ignore[union-attr]
            .distinct()
        ).all()
    )


def _sync_targets(session: Session, pages: list[Page]) -> list[Page]:
    """The brands a sync for these Pages has to fetch from.

    Not the same question as "which Pages am I looking at", and conflating the
    two is what froze Bodybuilding Tips N Tricks for 27 days. `fetch_competitor_
    posts` is per-`blogId`: a competitor's posts arrive only through the brand it
    sits under in Metricool, and which brand that is was decided by where the
    100-competitor allowance had room. Bodybuilding reads seven competitors, its
    own brand set is **empty**, and three of the seven are hosted by Fitness
    Girls — so Sync there asked for Bodybuilding's set, was correctly told it has
    none, and changed nothing while 241 current posts sat under a brand nobody
    had reason to open.

    The host is read from posts already stored rather than from Metricool, so
    this costs one query and no vendor call. Measured 2026-09-06:

        History Retraced   17 ticked -> History Retraced, The Fact Feed
        The Fact Feed      26 ticked -> History Retraced, The Fact Feed
        Bodybuilding        7 ticked -> Fitness Girls
        Fitness Recipes    15 ticked -> Fitness Girls

    The scope's own Pages are always included. That is what covers a competitor
    freshly added to this brand's set and ticked before anything of theirs has
    ever been fetched — there is no stored row to read a host from yet, and the
    overwhelmingly common case is that it was added right here.

    The gap it leaves: tick a competitor hosted by a brand that hosts nothing
    else you read, before any of its posts exist locally, and this will not
    reach it until some other sync stores one. Settings names the host brand on
    every pool row, which is the compensation; storing it on `page_competitor`
    would close it properly and costs a column and a migration.
    """
    scope_ids = [page.id for page in pages]
    hosts: set[int] = set()

    ticked = _assigned_to(session, scope_ids)
    if ticked:
        hosts = {
            host
            for host in session.exec(
                select(SourceItem.synced_for_page_id)  # type: ignore[arg-type]
                .where(SourceItem.kind == SourceKind.COMPETITOR_POST)
                .where(SourceItem.competitor_page_id.in_(ticked))  # type: ignore[union-attr]
                .distinct()
            ).all()
            if host is not None
        }

    wanted = hosts | set(scope_ids)
    return list(
        session.exec(
            select(Page).where(Page.id.in_(wanted)).order_by(Page.name)  # type: ignore[union-attr,arg-type]
        ).all()
    )


def _visible_to(session: Session, scope_ids: list[int]):
    """Which stored competitor posts these Pages may read.

    **Assignment decides, and nothing else does.** A post is visible to a Page
    because someone chose that competitor for it — which is the whole point,
    since Metricool's 100-competitor ceiling means the set a competitor happens
    to sit in says nothing about which Pages should read it.

    This used to fall back to provenance — `synced_for_page_id`, the sets those
    Pages own in Metricool — whenever a scope had no assignments at all. The
    fallback was a rollout concession: the moment the column existed every Page
    had zero assignments, and a strict reading would have blanked every grid
    until someone had ticked their way through Settings.

    It is removed because the concession outlived the rollout and was actively
    misleading. Two Pages read entirely different things through one screen with
    nothing on it saying which mode was in force, and the switch between them
    fired on the **first** assignment. Measured 2026-09-05:

        Fitness Girls   0 assignments, 484 posts on screen   (provenance)
        Bible Focus     1 assignment,    0 posts on screen   (assignment)

    Bible Focus is not the broken one — it is the honest one. Going from zero
    assignments to one collapsed a full grid to a single competitor, and that is
    exactly the bug that was reported against The Fact Feed: its `created_at`
    column shows one assignment at 2026-08-10 11:23:14, Ancient History
    Explorers, and twenty-five more added in one second at 14:50:06. For those
    three and a half hours the grid was that one competitor and nothing else,
    which is precisely what the operator saw and could not explain from Settings.

    A cliff at one assignment is worse than a floor at zero. Now the rule reads
    the same at every count: a Page shows what is ticked for it, so an empty grid
    means an empty tick list rather than a mode nobody was told about. The cost
    is that a Page with nothing assigned shows nothing — see `CompetitorReach`
    and the Sources empty state, which name that case rather than leaving it to
    look like a quiet week.
    """
    base = SourceItem.kind == SourceKind.COMPETITOR_POST
    return base & SourceItem.competitor_page_id.in_(  # type: ignore[union-attr]
        _assigned_to(session, scope_ids)
    )


class SourceSort(str, Enum):
    """How the grid is ranked. The operator's choice, not a constant.

    `REACTIONS` is the default and matches both Metricool's own Competitors tab
    and `fetch_competitor_posts`, which has always sorted this way before
    handing the rows over — the grid read was throwing that order away.
    """

    REACTIONS = "reactions"
    NEWEST = "newest"


@router.get("/competitors")
def get_competitor_posts(
    page_ids: list[int] | None = Query(
        None, description="Narrow to these Pages' competitor sets. Omit for all."
    ),
    refresh: bool = Query(False, description="Force a Metricool sync"),
    sort: SourceSort = Query(
        SourceSort.REACTIONS, description="Rank by reactions (default) or recency"
    ),
    session: Session = Depends(get_session),
) -> list[StoredSourceItem]:
    """Stored competitor posts across every Page, or a chosen subset.

    Not scoped to one Page. See `_scope` — Metricool caps an account at 100
    competitors in total, so the same source cannot be added to every Page that
    wants it, and the pool has to be shared.

    It used to sync on every read, which cost **5.5s and 1.6MB** for 500 posts
    to display 60 — against a seven-day window that gains roughly three posts an
    hour. Two reads ten minutes apart paid six seconds to learn nothing, and the
    grid was hostage to a vendor API that does sometimes time out.

    So the sync is explicit, matching the Refresh button the RSS tab already
    has. The empty case still syncs by itself, because a first-run operator
    should not have to know that a button is what makes the grid work.

    No time-based cooldown. A cooldown guesses at how stale is too stale; the
    operator looking at the grid knows, and the button is right there.

    **A sync fetches the brands that feed the scope, not the brands the scope
    is.** Those are different — see `_sync_targets`, which is where the reason
    lives. Syncing the scope's own brands is what left Bodybuilding Tips N Tricks
    27 days stale: its Metricool set is empty, so its Sync button fetched nothing
    while the competitors it reads were filling up under Fitness Girls. Sorting
    by Newest could not help either — nothing new had been stored to sort.

    Still one Metricool call per brand fetched, and the fetch is the expensive
    part. Measured 2026-09-06, whole account: 1,677 posts, **31.4s**, of which
    four brands account for 24s and six empty ones cost 1.3s each. Reaching only
    the hosts brings a Bodybuilding sync to one call, about 2.3s.

    Sequential on purpose. Threading would bound a full-account sync at its
    slowest brand — roughly 10s — and that is the fix to reach for if this grows,
    but it is concurrency added to a route that has none.
    """
    pages = _scope(session, page_ids)
    scope_ids = [page.id for page in pages]
    visible = _visible_to(session, scope_ids)

    # Counted across **every** competitor post, not the scope's own sets. This
    # question is "has a sync ever run", and the scoped count answered a
    # different one: a Page whose Metricool set is empty has zero of its own
    # posts permanently, so `stored == 0` held on every read and fired a vendor
    # call that fetched nothing, every time. Six of ten brands are in that state
    # today. Counting the pool makes this fire once, on a genuinely empty
    # database, which is the first-run case it was written for.
    stored = session.exec(
        select(func.count())
        .select_from(SourceItem)
        .where(SourceItem.kind == SourceKind.COMPETITOR_POST)
    ).one()

    if refresh or stored == 0:
        for page in _sync_targets(session, pages):
            try:
                fetched = metricool.fetch_competitor_posts(page)
            except metricool.MetricoolError as error:
                # 502: the failure is upstream, and saying so is what stops the
                # operator reading an empty grid as "no competitor posted this
                # week". One Page failing fails the read rather than returning a
                # partial pool silently — a quietly missing Page's worth of
                # sources is the same invisible gap, one level up.
                raise HTTPException(status_code=502, detail=str(error)) from error

            _upsert(session, fetched, refresh_volatile=True)
        session.commit()

    if sort is SourceSort.REACTIONS:
        # **Ranked by reactions, but only inside the lookback window.**
        #
        # The window is the whole reason this is safe, and dropping it brings
        # back the failure the old newest-only order existed to avoid. Reactions
        # is a *stable* ranking and nothing prunes `source_item` — History
        # Retraced's pool is 1,244 rows and grows daily — so ranking the whole
        # table and taking 60 freezes the grid on whatever went viral in July.
        # Measured on that pool: 42 of the top 60 unwindowed were already older
        # than the window, against 0 windowed.
        #
        # **Anchored to the newest post in scope, not to `now()`.** The obvious
        # version subtracts the window from the clock, and that returns an
        # *empty grid* for a Page whose pool has not been synced this week —
        # trading a stale ranking for no ranking, and an unexplained empty grid
        # is the failure this file already warns about twice. Anchoring to the
        # data means the answer is always "the best of the most recent week we
        # have", which is the same thing whenever the pool is fresh.
        windowed = [visible]
        newest_at = session.exec(
            select(func.max(SourceItem.published_at)).where(visible)
        ).one()
        if newest_at is not None:
            window = newest_at - timedelta(
                days=sources_config.competitors.lookback_days
            )
            windowed += [
                col(SourceItem.published_at).is_not(None),
                col(SourceItem.published_at) >= window,
            ]

        # **One competitor cannot own the grid.**
        #
        # A flat `ORDER BY reactions` was the whole ranking, and on a Page with
        # a loud competitor it turned 60 slots into one publisher's feed.
        # Measured 2026-09-05, top 60 by reactions:
        #
        #     Fitness Girls    59 of 60 David J Harris Jr.   18 authors in window
        #     The Fact Feed    33 of 60 Things You Don't Know 19 authors in window
        #     History Retraced 21 of 60 The Historian's Den   17 authors in window
        #
        # The Fact Feed reads 26 assigned competitors and 19 of them published
        # inside the window; 8 of those 19 reached the grid not at all. That is
        # the complaint — Settings says a Page reads many competitors and the
        # grid shows one — and it is not a data problem: every one of those posts
        # is stored, visible, and in the window. It simply lost 60 comparisons to
        # a page that gets 100x the reactions of everyone it is ranked against.
        #
        # So rank *within* each competitor first, and take a round at a time:
        # every competitor's best post before any competitor's second. The grid
        # opens on the strongest post from each of the 19, which is what "best of
        # the last 7 days" was supposed to mean — reactions still order each
        # round, so the loudest publisher still leads, it just cannot repeat
        # until everyone else has had a turn. Self-tuning: with two competitors
        # in the window they split 30/30, with sixty they get one each.
        #
        # Partitioned on `author`, not `competitor_page_id`, because 819 stored
        # rows predate that column and hold null — see `VOLATILE`. Those rows
        # carry the same author string as their backfilled siblings, so `author`
        # is the key that treats one competitor as one competitor.
        #
        # A window function rather than fetching the window and interleaving in
        # Python: History Retraced's window is 791 rows, and `grid_limit` exists
        # so that a grid read does not carry the pool across the wire.
        best_first = (
            # `published_at` descending is the tiebreak, so equal reactions still
            # read newest-first rather than by insertion order.
            col(SourceItem.reactions).desc().nulls_last(),
            col(SourceItem.published_at).desc(),
        )
        ranked = (
            select(
                col(SourceItem.id).label("id"),
                func.row_number()
                .over(partition_by=col(SourceItem.author), order_by=best_first)
                .label("rank"),
                col(SourceItem.reactions).label("reactions"),
                col(SourceItem.published_at).label("published_at"),
            )
            .where(*windowed)
            .subquery()
        )
        query = (
            select(SourceItem)
            .join(ranked, col(SourceItem.id) == ranked.c.id)
            .order_by(
                ranked.c.rank,
                ranked.c.reactions.desc().nulls_last(),
                ranked.c.published_at.desc(),
            )
        )
    else:
        # Newest first, unwindowed — a strict "what has arrived lately" read.
        # No window is needed because recency *is* the ranking here: the newest
        # 60 of a growing pool are recent by construction.
        #
        # Deliberately *not* interleaved by competitor. This order is a log, and
        # a log that has been reshuffled to look fair is no longer answering the
        # question it was asked. Reactions is a ranking, and a ranking is the
        # thing that owes every competitor a hearing.
        query = select(SourceItem).where(visible).order_by(
            col(SourceItem.published_at).desc()
        )

    rows = session.exec(query.limit(sources_config.competitors.grid_limit)).all()

    return _with_used(session, rows)


def _feeds_for(session: Session, page: Page) -> list[Feed]:
    """This Page's feeds, ordered by name. Empty is allowed, and it is a state.

    It used to raise — first a `KeyError` from the config loader, then a 500 —
    on the argument that an empty grid is indistinguishable from a quiet week.
    That was right while feeds were configuration: a Page with no entry in
    `sources.yml` was a misconfiguration nobody had noticed.

    It stopped being right when Pages became something you add. A new Page has
    no feeds by definition, and a 500 made its Settings screen unreachable —
    including the form that adds the first one. The screen says "no feeds yet"
    and offers the form; that is a legible empty state rather than silence,
    which is what the original rule was actually protecting against.
    """
    return list(
        session.exec(
            select(Feed).where(Feed.page_id == page.id).order_by(Feed.name)  # type: ignore[arg-type]
        ).all()
    )


def _with_used(session: Session, rows) -> list[StoredSourceItem]:
    """Flag the ones a Draft already came from, so the grid stops re-offering them."""
    spent = set(
        session.exec(
            select(Draft.source_item_id).where(Draft.source_item_id.is_not(None))  # type: ignore[union-attr]
        ).all()
    )
    return [
        StoredSourceItem(**row.model_dump(), used=row.id in spent) for row in rows
    ]


class CompetitorReach(BaseModel):
    """What actually reaches this Page's grid, and how much of it is off screen.

    An empty grid has three causes that look identical on screen, and the
    operator's next move is different for each: nobody is configured, somebody is
    configured but nothing has been synced, or everything is fine and the week was
    quiet. The client's round-4 note — "NONE from chosen posts were generated" —
    was sent about two Pages that have **zero** competitors in Metricool, and the
    grid said nothing at all.

    **Entirely local.** No Metricool call, deliberately: this is read at the
    moment the operator is already looking at an empty screen, and answering
    "why is this empty" with a 5.5s vendor round trip that has 502'd twice is the
    wrong trade. Everything here is a count over rows we already hold, so it
    cannot fail and cannot be slow.

    That costs one distinction — a Page with no competitors configured against a
    Page whose competitors have all gone quiet — and `assigned` recovers most of
    it, because assignment is a local fact.
    """

    assigned: int
    """`page_competitor` rows for the scope. Zero is now an empty grid.

    It used to mean the provenance fallback, and a Page could show a full grid
    on zero assignments. `_visible_to` says why that ended. The screen leans on
    this hardest in the zero case, because that is the one where Sync is not the
    answer and Settings is.
    """

    own_set_posts: int
    """Stored posts that arrived through these Pages' own Metricool sets.

    What a sync would have filled. No longer what the grid reads — it is kept
    because it is the difference between "nothing has arrived" and "plenty has
    arrived and none of it is ticked", which are the two halves of an empty grid
    and want opposite next moves. Zero alongside `assigned == 0` is the state
    worth naming out loud: nothing reaches this Page at all, and no amount of
    pressing Sync will change that.
    """

    visible_posts: int
    """Everything these Pages may read, before the reactions window narrows it.

    Zero here is exactly the condition that empties the grid, so the screen can
    trust this rather than inferring from a list length it also has to sort.
    """

    used_posts: int
    """Distinct sources these Pages have actually generated from.

    `_with_used` marks them, but only across the `grid_limit` rows the grid
    returns — 60, against History Retraced's 808 visible — so a post ticked
    yesterday has usually dropped out of the window by the time the operator
    comes back, and its marker with it. Measured 2026-08-17:

        Bodybuilding Tips N Tricks   3 drafts from sources   0 markers in grid
        History Retraced            31 drafts from sources   2 markers in grid
        The Fact Feed                2 drafts from sources   0 markers in grid

    That is the reading behind "NONE from chosen posts were generated": the one
    screen that could have shown otherwise was showing zero.

    **Counted from the Pages' drafts, not from the visible pool.** Intersecting
    with `_visible_to` was the first version and it answered **0** for
    Bodybuilding Tips N Tricks — the Page the complaint is about — because its
    three used sources are no longer visible to it at all. A count that goes
    quiet in exactly the case it exists for is worse than no count. Distinct,
    because two drafts from one post is one used source, which is what the
    grid's marker means.
    """


@router.get("/competitors/reach")
def get_competitor_reach(
    page_ids: list[int] | None = Query(
        None, description="Narrow to these Pages. Omit for all."
    ),
    session: Session = Depends(get_session),
) -> CompetitorReach:
    pages = _scope(session, page_ids)
    scope_ids = [page.id for page in pages]
    visible = _visible_to(session, scope_ids)

    def count(where) -> int:
        return session.exec(
            select(func.count()).select_from(SourceItem).where(where)
        ).one()

    return CompetitorReach(
        assigned=session.exec(
            select(func.count())
            .select_from(PageCompetitor)
            .where(PageCompetitor.page_id.in_(scope_ids))  # type: ignore[union-attr]
        ).one(),
        own_set_posts=count(
            (SourceItem.kind == SourceKind.COMPETITOR_POST)
            & SourceItem.synced_for_page_id.in_(scope_ids)  # type: ignore[union-attr]
        ),
        visible_posts=count(visible),
        used_posts=session.exec(
            select(func.count(func.distinct(Draft.source_item_id))).where(
                col(Draft.page_id).in_(scope_ids),
                col(Draft.source_item_id).is_not(None),
            )
        ).one(),
    )


@router.get("/items/{item_id}")
def get_source_item(
    item_id: int, session: Session = Depends(get_session)
) -> SourceItem:
    """One stored Source Item by id — what a Draft was generated from.

    `Draft.source_item_id` has been on the wire since the first day and no screen
    could turn it into a sentence, which is the whole of the client's round-4
    note: "I have no idea which source or which competitor posts the tool gens
    content from." 35 of 38 drafts carry one. The answer was a foreign key
    nothing rendered.

    Read one row at a time by the review drawer rather than joined onto the
    Draft, because the Draft response has no room for it. Every route that
    returns a Draft returns the table class directly, so attaching a source would
    mean either a wrapper model on all ten of them — and the field coming back
    null from every mutation route, so the line blinks out the moment you press
    Save — or a `Relationship`, which SQLModel does not serialise on a
    `table=True` model at all.

    Only stored kinds resolve, which is every kind a Draft can point at: a tweet
    or an RSS item becomes a row when a run uses it (`generate.resolve_sources`),
    so a Draft never references something that was only ever browsed.
    """
    item = session.get(SourceItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"No source item {item_id}")
    return item


@router.get("/rss")
def get_rss(
    page_id: int = Query(...),
    session: Session = Depends(get_session),
) -> RssFeedOut:
    """This Page's curated feeds, live. Nothing is written.

    Takes a `page_id` because the feed list is per-page — the beats do not
    overlap, and hot tub news is noise on a history grid. Unlike competitor
    posts, which are a shared pool: see `_scope`. A feed costs nothing to list
    against two Pages, and Metricool's competitor ceiling has no equivalent here.
    """
    page = session.get(Page, page_id)
    if page is None:
        raise HTTPException(status_code=404, detail=f"No page {page_id}")

    feeds = _feeds_for(session, page)
    feed = rss.fetch_rss(feeds)

    return RssFeedOut(
        items=feed.items,
        failures=[
            FeedFailureOut(feed_url=failure.feed_url, error=failure.error)
            for failure in feed.failures
        ],
    )


class SourcesConfigOut(BaseModel):
    """What a run is configured with, for the Settings screen.

    Two halves now, and they no longer come from the same place: the windows are
    `config/sources.yml`, the feeds are rows. Served from the parsed model and
    the table rather than described a second time on the client, for the reason
    `routes/config.py` gives about `layout.yml` — a screen whose whole job is to
    show what a run is configured with must not show a hand-kept copy that can
    disagree with it.

    Deliberately **separate** from the competitor list below. This half is local
    and cannot fail; that half is a vendor call that has 502'd twice. Bundling
    them would let Metricool being down blank the feed list too.
    """

    since_days: int
    max_items: int
    feeds: list[Feed]
    """This Page's, not every Page's — the beats do not overlap."""

    lookback_days: int
    grid_limit: int


@router.get("/config")
def get_sources_config(
    page_id: int = Query(...),
    session: Session = Depends(get_session),
) -> SourcesConfigOut:
    page = session.get(Page, page_id)
    if page is None:
        raise HTTPException(status_code=404, detail=f"No page {page_id}")

    return SourcesConfigOut(
        since_days=sources_config.rss.since_days,
        max_items=sources_config.rss.max_items,
        feeds=_feeds_for(session, page),
        lookback_days=sources_config.competitors.lookback_days,
        grid_limit=sources_config.competitors.grid_limit,
    )


class CompetitorOut(BaseModel):
    """One configured competitor, and whether it is actually producing."""

    id: int | None = None
    """Metricool's own row id. What `DELETE /competitors/{id}` takes — their
    parameter is `competitorId` and means their key, not Facebook's."""

    provider_id: str
    name: str
    followers: int | None = None
    picture: str | None = None
    """Facebook's CDN, signed and expiring in about four days. Passed straight
    through and never stored — this list is re-read live on every request, so
    the URL is always fresh. See the note in `sources/metricool.py`."""

    posts_stored: int
    """How many of this competitor's posts are stored, within the scope asked for.

    Zero is the interesting value and the reason this endpoint exists: a
    competitor configured in Metricool that has published nothing looks exactly
    like one that was never configured, from every other screen. Counted from
    stored rows rather than a second posts fetch — the sync already paid 1.6MB
    for them, and they are what the grid shows.
    """

    assigned_page_ids: list[int] = []
    """Which of our Pages read this competitor. The editable half of this row.

    Empty means nobody reads it, full stop. It used to mean less than that: a
    Page holding no assignments read its whole brand set through the provenance
    fallback, so an unassigned competitor was often still being read, and this
    field was accompanied by a `reads_by_default` flag saying which of the two
    was in force. `_visible_to` dropped the fallback on 2026-09-05 and the flag
    went with it — there is one state now, and it is this list.
    """

    page_id: int
    page_name: str
    """Which Page's competitor set this belongs to in Metricool.

    Worth showing now that the pool is shared. A source added under one Page is
    read by all of them, so "which set is it in" stops being a property of who
    can use it and becomes a fact about where the allowance was spent — which is
    the thing to look at when the account approaches Metricool's ceiling of 100
    competitors *in total*.
    """


@router.get("/competitors/pages")
def get_competitor_pages(
    page_ids: list[int] | None = Query(
        None, description="Narrow to these Pages' competitor sets. Omit for all."
    ),
    session: Session = Depends(get_session),
) -> list[CompetitorOut]:
    """Every Page's competitor set, live from Metricool, or a chosen subset.

    Defaults to all Pages because the number that matters is the account total:
    Metricool allows 100 competitors across the whole account, and this is the
    only screen where that budget is visible.

    The list is Metricool's and is not stored (see `CONTEXT.md`: the agent
    stores their posts, never the list itself), so this reads it every time.
    `fetch_competitors` was written for exactly this question and had no caller
    until now.

    Joined to stored posts on the competitor's display name. That is the same
    field the posts carry as `ownerDisplayName`, and it matches exactly: across
    both Pages, 48 configured competitors and 40 distinct post authors, every
    author resolved and none unmatched in either direction.
    """
    pages = _scope(session, page_ids)

    counts = dict(
        session.exec(
            select(SourceItem.author, func.count(SourceItem.id))  # type: ignore[arg-type]
            .where(
                SourceItem.kind == SourceKind.COMPETITOR_POST,
                SourceItem.synced_for_page_id.in_([page.id for page in pages]),  # type: ignore[union-attr]
            )
            .group_by(SourceItem.author)  # type: ignore[arg-type]
        ).all()
    )

    # Every assignment, not just this scope's: the screen shows which Pages read
    # a competitor, and narrowing to the scope would hide the Page that is
    # actually reading it.
    assignments: dict[str, list[int]] = {}
    for row in session.exec(select(PageCompetitor)).all():
        assignments.setdefault(row.competitor_page_id, []).append(row.page_id)

    rows = []
    for page in pages:
        try:
            competitors = metricool.fetch_competitors(page)
        except metricool.MetricoolError as error:
            # 502: the competitor set is somebody else's, and the screen says so
            # rather than pretending the set is empty.
            raise HTTPException(status_code=502, detail=str(error)) from error

        assert page.id is not None
        rows.extend(
            CompetitorOut(
                id=competitor.get("id"),
                provider_id=competitor["provider_id"],
                name=competitor["name"],
                followers=competitor["followers"],
                picture=competitor.get("picture"),
                posts_stored=counts.get(competitor["name"], 0),
                assigned_page_ids=assignments.get(competitor["provider_id"], []),
                page_id=page.id,
                page_name=page.name,
            )
            for competitor in competitors
        )

    # Silent ones first: they are the finding, and at the bottom of forty-eight
    # rows they would be exactly as invisible as they are today.
    rows.sort(key=lambda row: (row.posts_stored, -(row.followers or 0)))
    return rows


@router.get("/tweet")
def get_tweet(url: str = Query(...)) -> SourceItemBase:
    """One live lookup. Nothing is written, and the X API is paid per read."""
    try:
        return x.fetch_tweet(url)
    except x.XError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


VOLATILE = ("image_url", "reactions", "comments", "shares", "competitor_page_id")
"""Facts the vendor owns and keeps changing, as opposed to the content chosen.

`image_url` is the reason this list exists. Facebook's CDN URLs are *signed and
expire* — the `oe` parameter on a freshly synced one is about four days out,
while the competitor window is seven. Frozen at first sync, every image in the
grid would break before it left the window. The old system refreshed these on
every sync (`competitorMetricoolSyncService.ts:203`), and it was right to.

`text` is deliberately not here. Metrics and a CDN URL are the vendor's; the
words are what the operator chose, and rewriting them under a Draft that already
used them would make the Draft's provenance a moving target.

`competitor_page_id` is the odd one out: it never changes, so it is not volatile
in the sense the rest of this list means. It is here because 954 rows predate the
column and hold null, and a null there is not a cosmetic gap — `_visible_to`
matches assignments on it, so a Page with an assignment and un-backfilled posts
shows an **empty grid**. Which is exactly what happened. Refreshing it on sync is
what repairs those rows.
"""


def _upsert(
    session: Session,
    items: list[SourceItemBase],
    refresh_volatile: bool = False,
) -> list[SourceItem]:
    """One row per item, existing or new. Does not commit.

    Existing rows keep their content. `refresh_volatile` additionally updates
    `VOLATILE` — set by the competitor sync, which is re-reading the same posts
    from the vendor, and not by `POST /sources`, where the client is handing
    back a body it was shown rather than a fresh read.
    """
    rows: list[SourceItem] = []
    # Looked up in one query, not one per item. A competitor sync carries 500
    # posts, and a lookup each made this route 502 statements.
    pending = _existing_by_key(session, items)

    for item in items:
        key = (item.kind, item.external_id)
        existing = pending.get(key)

        if existing is None:
            existing = SourceItem(**item.model_dump())
            session.add(existing)
            # Items within one call can collide too — the same story in two
            # feeds — and the flush that would surface it has not happened yet.
            pending[key] = existing
        elif refresh_volatile:
            for field in VOLATILE:
                setattr(existing, field, getattr(item, field))
            session.add(existing)

        rows.append(existing)

    return rows


_CHUNK = 500
"""SQLite caps host parameters per statement. The modern default is 32766, but
older builds ship 999 and this runs on whatever Python bundles."""


def _existing_by_key(
    session: Session, items: list[SourceItemBase]
) -> dict[tuple[SourceKind, str], SourceItem]:
    """Rows that already exist, keyed by `(kind, external_id)`.

    Filtered on `external_id` alone and paired up in Python: one indexed `IN`
    beats a composite match, and an `external_id` colliding across two kinds is
    not a thing that happens — a Facebook post id is not a feed URL.
    """
    wanted = sorted({item.external_id for item in items if item.external_id})
    found: dict[tuple[SourceKind, str], SourceItem] = {}

    for start in range(0, len(wanted), _CHUNK):
        chunk = wanted[start : start + _CHUNK]
        for row in session.exec(
            select(SourceItem).where(SourceItem.external_id.in_(chunk))  # type: ignore[union-attr]
        ).all():
            found[(row.kind, row.external_id)] = row

    return found
