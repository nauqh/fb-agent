"""The four tables. See docs/data-model.md for why there are so few.

Nothing here carries a user_id (ADR-0002), a brand_key (ADR-0003), or any
schedule state (ADR-0001). Layout lives in config/layout.yml, not on Page.

`Feed` is the one that data-model.md rejected and this file now has. The
rejection still reads correctly on its own terms — nothing points at a feed —
but it was answering "does a feed need identity", and the question that brought
the table back is different: the operator has to be able to add and remove one
without a deploy. `config/sources.yml` cannot answer that, because the API runs
from a container image on Railway and a file written into it is gone at the next
deploy, with the repo's committed copy silently disagreeing in the meantime.
"""

from datetime import datetime, timezone
from enum import StrEnum

from pydantic import computed_field
from sqlalchemy import Enum as SAEnum
from sqlmodel import JSON, Column, Field, SQLModel, UniqueConstraint

from app import media


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _stored_enum(enum: type) -> SAEnum:
    """How an enum column is stored: `VARCHAR`, never a native Postgres type.

    Three things have to hold at once, and the obvious spellings each break one:

    - **The two backends must build the same schema.** Left to its default,
      SQLAlchemy emits `CREATE TYPE … AS ENUM` on Postgres and a plain string on
      SQLite, so the offline test suite would be exercising a schema production
      does not have.
    - **Adding a value should not need a migration at all.** Alembic arrived
      after this was written, so `ALTER TYPE` is now a migration we *could*
      write — but a new member is a fact about the Python enum, and having it
      also be a schema change is a cost with nothing on the other side.
      `create_constraint` is left off for the same reason: a `CHECK` listing the
      values would need altering too.
    - **It must load back as the enum, not as `str`.** `sa_type=String` gets the
      first two and silently loses this one: `SourceKind.is_factual` is a
      property, `sources/__init__.py` asks for it on a value read from the
      database, and a bare string raises `AttributeError` mid-run. The tests did
      not catch it — they construct their rows rather than reloading them — so
      it would have shipped.

    `length` is fixed rather than derived. SQLAlchemy sizes the column to the
    longest *current* value, so a longer member added later would need an
    `ALTER TABLE` — `alembic check` would catch it now, but 32 is clear of every
    value either enum has and there is nothing to catch.
    """
    return SAEnum(enum, native_enum=False, length=32, values_callable=lambda e: [m.value for m in e])


class SourceKind(StrEnum):
    COMPETITOR_POST = "competitor_post"
    TWEET = "tweet"
    RSS = "rss"

    @property
    def is_factual(self) -> bool:
        """Whether the *subject* binds the writer.

        A competitor post is borrowed for tone only; a tweet or an RSS item must
        produce a post about that same story. Reversing this tells the model to
        treat a Smithsonian piece as a writing sample. Derived, never stored — a
        stored copy is a second truth, and when it drifts the model still
        returns confident, well-formed output about the wrong story.
        """
        return self is not SourceKind.COMPETITOR_POST


class DraftStatus(StrEnum):
    GENERATING = "generating"
    REVIEW = "review"
    APPROVED = "approved"
    REJECTED = "rejected"
    FAILED = "failed"
    """The run did not produce a draft. `error` says why.

    Separate from `review` because a run that produced nothing is not a draft
    awaiting a decision. It used to land in `review`, which put empty rows in the
    queue beside real ones, looking ready — the operator's only clue was an
    `error` column nothing rendered.
    """


class Page(SQLModel, table=True):
    """An owned Facebook page. Rows, not constants — adding one is an insert.

    v1 runs **one** page, History Retraced. The table stays rather than becoming
    a constant because `draft.page_id` and `source_item.synced_for_page_id`
    point at it; adding the second page should be an insert, not a schema change
    plus a rewrite of every query (ADR-0003).

    Identity and policy only. The prompts moved to `api/prompts/*.txt` — see
    app/writer/prompts.py. There is no `is_active`: with one page it is always
    true, and a flag that is never false is not state.
    """

    __tablename__ = "page"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(unique=True, index=True)
    facebook_page_id: str = Field(unique=True, index=True)
    metricool_blog_id: str | None = None

    avatar_image_path: str | None = None
    """The page's profile picture, relative to `API_DIR`. Round, on white.

    Not the watermark: that is a white-ink wordmark for stamping onto a
    photograph, and a circular crop of it is a fragment of a word on a black
    disc. This is the same wordmark on white, which is what Facebook shows
    beside the page name and what the queue and the feed preview both draw.
    """

    avatar_url: str | None = None
    """The brand's logo as Metricool serves it. UI only, never the composite.

    `static.metricool.com`, and deliberately not the Facebook CDN URL beside it:
    those are signed and expire in about four days, which is the trap the
    competitor pictures document. These carry no signature and only a `v=` cache
    buster, so they survive.

    Still second to `avatar_image_path`. A committed file cannot 404, and the
    two Pages that have one are the two whose artwork someone actually made. The
    URL is what stops the other eight rendering as a grey initial.

    Explicitly **not** a watermark source. That is stamped into published images
    and must be a committed file — the old system read it from a bucket, the
    bucket was cleared, and the compositor quietly printed the page name instead
    for months. A round profile picture is also the wrong artwork: the watermark
    is a white wordmark on a photograph, not an avatar.
    """

    watermark_image_path: str | None = None
    """The page's own logo, relative to `API_DIR` — a committed asset, not a
    bucket object, so a clone has it and no fetch can fail on it.

    Committed rather than hosted because the hosted one is exactly what failed:
    the old system kept it in Supabase Storage and read it back by key, and when
    the bucket was cleared every path started returning `NoSuchKey`. The
    compositor swallows that (`return null`, image-composite.ts:136) and quietly
    prints the page name as text instead, so the logo vanished from output with
    nothing raised. See docs/data-model.md for where the file was recovered from.

    Null still means "no logo, render the name as text" — but only as a
    deliberate choice for a page without one, never as cover for a broken path.
    """

    watermark_upload_path: str | None = None
    """An uploaded mark, bucket-relative. Wins over the committed asset.

    Hosting the watermark is what failed in the old system, so this exists only
    because the failure was never the hosting: it was that the compositor
    *swallowed* a missing object and printed the page name instead. Ours raises
    (`compositor._watermark`), so a cleared bucket is a failed draft with a
    sentence naming the file, not eight months of unmarked posts.

    It is a second source rather than a replacement because the committed asset
    cannot 404 and needs no upload — two Pages already have one. This is the
    answer for the other eight, whose artwork is not in the repo and whose
    operator cannot commit a file.
    """

    watermark_text: str | None = None
    """What to print when the Page has no image mark. Null means its `name`.

    A column and not a constant because the name is the Metricool brand's — "GYM
    Motivation | quotes | videos | tips|" is one of the ten, and that is not what
    anyone wants stamped on a photograph.

    Reached only when neither an upload nor a committed asset is set. A
    configured image that will not load raises instead of falling through to
    this, which is the single difference from the old compositor: there, a
    missing file quietly became text and the logo was gone from output for
    months with nothing failing.
    """

    badge_text: str | None = None
    """The headline chip's word — "NEWS", "HISTORY". Null draws no badge.

    Drawn on `full_overlay` cards only, where the panel lies over the photograph
    and there is room above it. Per Page rather than per draft, for now: one word
    that says what the Page publishes is most of the value, and a label chosen
    per post needs the writer to return one and the review drawer to edit it.

    Not in `layout.yml` beside the badge's colour and size, because those are
    style and this is a word: "NEWS" on a history page is wrong in a way no
    layout value can be.
    """

    watermark_enabled: bool = Field(default=True)
    """Whether this Page's cards get a mark at all. Off means a clean image.

    Separate from having no mark configured: a Page with neither an image nor
    its own text still draws its *name*, because unmarked output is how a
    picture ends up reposted with no idea where it came from. This is the
    deliberate opt-out for the operator who wants the photograph alone, and it
    silences the image and the text together — a half-off switch that still
    printed the name would be the confusing one.
    """

    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)

    def watermark(self) -> tuple[str | bytes | None, str | None]:
        """What to stamp, and what to print if there is nothing to stamp.

        One method rather than two expressions at each call site, because the
        two answers are one decision: `(None, None)` when the Page is opted out,
        and otherwise the mark in precedence order — upload, committed asset,
        then the text, which falls back to the Page's name.

        The upload is *fetched* here, so a cleared bucket raises at the caller
        rather than resolving to a path the compositor draws nothing for. That
        is the whole difference from the old system, which swallowed the miss
        and printed the name for months while looking like it was working.
        """
        if not self.watermark_enabled:
            return None, None
        return (
            media.watermark_source(
                self.watermark_upload_path, self.watermark_image_path
            ),
            self.watermark_text or self.name,
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def watermark_upload_url(self) -> str | None:
        """Where the browser fetches an uploaded mark. Null for a committed one.

        The committed asset is not a bucket object and has no public URL — the
        screen reaches it through the API's own `/assets` mount, which the Next
        proxy authenticates. Only the uploaded one is built here, for the same
        reason the Draft URLs are: one place knows what a bucket is.
        """
        return (
            media.public_url(self.watermark_upload_path)
            if self.watermark_upload_path
            else None
        )


class Feed(SQLModel, table=True):
    """One RSS feed a Page draws from. Rows, so they can be added and removed.

    Per-page because the beats do not overlap — the old system's four brands
    were history, general facts, scripture and hot tubs, and hot tub news is
    noise on a history grid.

    Nothing points at a row here. `SOURCE_ITEM` still carries the publisher as
    `author` rather than a `feed_id`, exactly as data-model.md argued: an item
    outlives the feed it arrived through, and a foreign key would make removing
    a feed either a cascade through published work or an error message about
    drafts from 2026. Deleting a Feed removes it from tomorrow's grid and
    changes nothing that already happened.
    """

    __tablename__ = "feed"
    __table_args__ = (
        # The same URL twice on one Page is not a second source, it is one
        # source counted twice — `_merge` deduplicates the items, so the only
        # visible effect would be a wasted fetch and a duplicate row on Settings.
        UniqueConstraint("page_id", "url", name="uq_feed_page_url"),
    )

    id: int | None = Field(default=None, primary_key=True)
    page_id: int = Field(foreign_key="page.id", index=True)

    name: str
    """The byline, and the reason this is not derived from the feed itself.

    Curated rather than taken from the feed's own <title>, which is written for
    feed readers and reads badly on a card — "History | smithsonianmag.com",
    "Archaeology News -- ScienceDaily". It reaches the writer as the publisher.
    """

    url: str

    note: str | None = None
    """Why this feed earns its place — item count, summary length, whether it
    carries images.

    A column rather than a comment because the comments are where this
    evidence used to live: `config/sources.yml` carried a probe result above
    every entry ("31 items, 179-char summaries, every item imaged") and a
    rejection list beside them. Moving the feeds into a table without this would
    have thrown all of that away at the first `git rm`. The seed migration
    carries the twelve original notes across verbatim.
    """

    created_at: datetime = Field(default_factory=_now)


class SavedPost(SQLModel, table=True):
    """A published post kept on purpose, for reference or reuse.

    **The one thing on the Overview screen that needs a table.** Performance is
    read live from Metricool and cached by nothing; this is not that. A saved
    post is a decision — "this one worked, write more like it" — and it has to
    outlive the analytics window it was found in. Metricool's `/stats` call
    takes a date range, so a post drops out of every read once it is old enough,
    and a reference that vanishes on a rolling window is not a reference.

    The metrics are copied in, deliberately. They are **what the post scored
    when it was saved**, not a live figure — a snapshot is the honest thing to
    show beside "saved 3 months ago", and re-reading them would need the post to
    still be inside the window it has by definition left.

    Not a `Draft`. Most of these were published by the old app or written in
    Metricool's composer and have no draft of ours behind them; `draft_id` is
    there for the ones that do.
    """

    __tablename__ = "saved_post"
    __table_args__ = (
        # Saving the same post twice is one decision recorded twice. The UI
        # toggles on this, so the constraint is what makes the toggle honest.
        UniqueConstraint("page_id", "metricool_post_id", name="uq_saved_post_page_post"),
    )

    id: int | None = Field(default=None, primary_key=True)
    page_id: int = Field(foreign_key="page.id", index=True)

    metricool_post_id: str = Field(index=True)
    """Facebook's own `postId` as Metricool reports it (`<pageId>_<postId>`).
    The join back to a stats row, and stable in a way a permalink is not."""

    text: str = ""
    permalink_url: str | None = None
    picture_url: str | None = None
    """Facebook's CDN URL, which **expires**. Kept for the thumbnail and
    expected to rot: the competitor pictures document the same trap. A saved
    post whose thumbnail has gone is still a saved post, so nothing here treats
    a broken image as a broken row."""

    published_at: datetime | None = None

    reactions: int = 0
    comments: int = 0
    shares: int = 0
    impressions: int = 0
    """What it scored **when saved**. A snapshot, never refreshed — see above."""

    note: str | None = None
    """Why this one was worth keeping. The whole point of saving it."""

    created_at: datetime = Field(default_factory=_now)

    draft_id: int | None = Field(default=None, foreign_key="draft.id", index=True)
    """Ours, when the post came from this app. Null for everything else."""


class PageTimeSlot(SQLModel, table=True):
    """One time of day this Page publishes at. The same times every day.

    **This is not schedule state and does not reverse ADR-0001.** The ADR is
    about mirroring Metricool's planner — what is queued, when, and whether it
    went out — and none of that is here. A slot is *policy*: "we post at 08:00
    and 19:00", a standing decision that exists whether or not anything is
    queued against it. Metricool has nowhere to keep it and no concept of it.

    Nothing points at a row here, deliberately. A scheduled post records its own
    time in the planner, so deleting a slot changes tomorrow's suggestion and
    nothing that already happened — the same shape as `Feed`.

    No weekday column. The operator chose the same times every day; a weekday
    dimension doubles the table and the form for a distinction they did not
    ask for, and adding one later is an additive migration.
    """

    __tablename__ = "page_time_slot"
    __table_args__ = (
        # The same time twice is not two slots, it is one slot counted twice —
        # and "next available" would then offer it, find it taken, and offer it
        # again on the next pass.
        UniqueConstraint("page_id", "minute_of_day", name="uq_time_slot_page_minute"),
    )

    id: int | None = Field(default=None, primary_key=True)
    page_id: int = Field(foreign_key="page.id", index=True)

    minute_of_day: int = Field(index=True)
    """Minutes past midnight, 0–1439, in the Page's zone (`settings.timezone`).

    An integer rather than a `TIME` column, and rather than an `HH:MM` string.
    A `TIME` invites the question of which date and therefore which offset it
    carries, which is exactly the confusion the timezone rules in `CLAUDE.md`
    exist to prevent — there is no instant here, only a time of day. A string
    would need parsing before it could be sorted or compared, and "8:00" would
    sort after "19:00".

    Every clock in this app is `Asia/Ho_Chi_Minh` and this is no exception.
    """

    created_at: datetime = Field(default_factory=_now)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def label(self) -> str:
        """`HH:MM`, for a screen that should not do arithmetic to show a time."""
        return f"{self.minute_of_day // 60:02d}:{self.minute_of_day % 60:02d}"


class PageCompetitor(SQLModel, table=True):
    """Which Competitors feed which Pages. Ours, not Metricool's.

    This is not a mirror of Metricool's competitor list, and `CONTEXT.md`'s rule
    survives intact: the list is still configured there and still never stored
    here. What is stored is an *assignment* on top of it — a decision only this
    app can hold, because Metricool has no concept of one competitor serving
    several of your pages.

    It exists because of a hard external limit. A Metricool account may
    configure 100 competitors **in total**, not per page. Five politics Pages
    that should each watch the same twenty sources would need those twenty added
    five times, spending the entire allowance on twenty distinct sources. So a
    competitor is added once, under whichever Page has room, and assigned here to
    every Page that should read it.

    No foreign key to a competitor row, because there is no competitor table and
    should not be — the list is Metricool's. `competitor_page_id` is their
    `providerId`, and an assignment naming a competitor that has since been
    removed there is harmless: it matches no posts and shows on Settings as a row
    Metricool no longer lists.
    """

    __tablename__ = "page_competitor"
    __table_args__ = (
        UniqueConstraint(
            "page_id", "competitor_page_id", name="uq_page_competitor_page_provider"
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    page_id: int = Field(foreign_key="page.id", index=True)
    competitor_page_id: str = Field(index=True)
    """Metricool's `providerId`. Joins to `source_item.competitor_page_id`."""

    name: str | None = None
    """The competitor's display name when the assignment was made.

    A convenience for showing an assignment whose competitor Metricool no longer
    lists — without it such a row renders as a bare id. Never used to join;
    `competitor_page_id` is the key precisely because names change.
    """

    note: str | None = None
    """Why this Page reads this competitor.

    Here because a table has no history and a config file does. Keeping the
    mapping in `sources.yml` was considered for exactly that reason — `git log`
    would say who decided a Page should read a competitor, and why — and rejected
    because it would put this behind a deploy while the feed list, the other half
    of the same Settings screen, is editable from a form. Two ways to change two
    similar settings is worse than one missing changelog.

    This column is the compensation, and it is the same trade `Feed.note` makes:
    the reasoning travels with the row instead of with the commit. Optional,
    because an obvious assignment does not need defending.
    """

    created_at: datetime = Field(default_factory=_now)


class PageLayout(SQLModel, table=True):
    """One Page's overrides to the Composed Image. Null means "use the default".

    `config/layout.yml` is the default and stays in git; a row here holds only
    what a Page changed, and the renderer resolves `{**yaml, **row}`. Resetting
    a Page is deleting its row, which is why every column is nullable rather
    than seeded with the current values — a row full of copied defaults would
    silently stop tracking a change to the file.

    **This reverses a decision, deliberately.** `config/layout.yml` said it "has
    no per-page section and should not grow one", and `CONTEXT.md` said a Page
    "does not own styling — every Page renders in the same form and size". Both
    were written when there was one Page. Two Pages with unrelated beats, and an
    operator who wants a news card to look unlike a history card, is new
    evidence rather than a lapse. Both files now say so.

    Image dimensions and the font are **not** here, and that part of the old
    decision holds: 4:5 is the tallest ratio Facebook renders in feed, and a
    font family that does not match the TTF's name table makes resvg substitute
    a serif silently and still return a valid PNG. Neither failure is visible
    from a form.
    """

    __tablename__ = "page_layout"

    id: int | None = Field(default=None, primary_key=True)
    page_id: int = Field(foreign_key="page.id", unique=True, index=True)

    template: str | None = None
    """`card` or `full_overlay`. The one override that changes the geometry.

    A column like the rest rather than a Page field, because it is a layout
    value: null means the Page tracks `layout.yml`, and resetting the Page
    returns it to whatever the file says — the same contract every other
    override here has.
    """

    panel_ratio: float | None = None
    panel_max_ratio: float | None = None
    panel_color: str | None = None
    panel_opacity: float | None = None

    text_font_size_px: int | None = None
    text_line_height_ratio: float | None = None
    text_align: str | None = None
    text_color: str | None = None
    text_uppercase: bool | None = None
    """Draw the panel in capitals. Null tracks `layout.yml`, which says no.

    Three-valued on purpose, like every column here: `False` is a Page that has
    decided against capitals and will not follow the file if the file changes,
    and `None` is a Page that has not decided. `_merge` skips only `None`, so
    the difference survives resolution.
    """
    text_padding_left_px: int | None = None
    text_padding_right_px: int | None = None
    text_padding_top_px: int | None = None
    text_padding_bottom_px: int | None = None

    highlight_color: str | None = None

    watermark_max_px: int | None = None
    watermark_top_ratio: float | None = None

    badge_color: str | None = None
    badge_font_size_px: int | None = None

    portrait_size_px: int | None = None
    portrait_min_px: int | None = None
    portrait_max_width_ratio: float | None = None
    portrait_ring_pad_px: int | None = None
    portrait_border_width_px: int | None = None
    portrait_border_color: str | None = None

    updated_at: datetime = Field(default_factory=_now)


class SourceItemBase(SQLModel):
    """A Source Item's content, with no identity yet.

    This is what an adapter returns and what the client posts back. It exists
    because **browsing does not write**: an RSS item or tweet is fetched live and
    shown in the grid long before — and usually without ever — becoming a row,
    so the unsaved shape needs a type of its own rather than a `SourceItem` with
    a fake id.

    Splitting it here rather than declaring the fields twice is what keeps the
    two from drifting; adding a column to `SourceItem` alone would silently stop
    the adapters from being able to supply it.
    """

    kind: SourceKind = Field(index=True, sa_type=_stored_enum(SourceKind))
    """Stored as `VARCHAR`, loaded back as `SourceKind` — see `_stored_enum`.

    Loading it back as the enum is load-bearing rather than tidy: `is_factual`
    is a property on this class, and `sources/__init__.py` asks for it to decide
    whether a Source Item's subject binds. A plain string there is an
    `AttributeError` in the middle of a generate run.
    """

    external_id: str
    author: str | None = None
    """Competitor page name, X handle, or publisher."""

    synced_for_page_id: int | None = Field(
        default=None, foreign_key="page.id", index=True
    )
    """Which Page's Metricool competitor set this arrived through. Provenance.

    It used to be ownership — the Competitors grid filtered on it — and that was
    wrong for a reason outside this codebase: Metricool caps an account at 100
    competitors *in total*, so five Pages that should each watch the same twenty
    sources cannot each be given them. Which set a competitor sits in is a fact
    about where the allowance was spent, not about who may read it.

    Which Pages a competitor actually feeds is `page_competitor` now.
    """

    competitor_page_id: str | None = Field(default=None, index=True)
    """The competitor's own Metricool `providerId`. competitor_post only.

    The join key between a stored post and an assignment. Measured before it was
    relied on: across History Retraced's window, all 15 distinct post `pageId`
    values are `providerId`s from the competitor list, none unmatched.

    Not the display name, which is what the Settings screen joined on first.
    That matches today and breaks silently the day a competitor renames itself —
    the posts keep arriving under the new name and every count against the old
    one quietly reads zero, which is indistinguishable from a page that stopped
    posting.
    """

    text: str = ""
    url: str | None = None
    image_url: str | None = None
    published_at: datetime | None = None

    reactions: int | None = None
    comments: int | None = None
    shares: int | None = None
    """Null for tweets and RSS items. Reactions is the default sort on Competitors."""


class SourceItem(SourceItemBase, table=True):
    """External material selected as input. One table, three kinds."""

    __tablename__ = "source_item"
    __table_args__ = (
        # Ticking the same RSS item twice must not create a second row.
        UniqueConstraint("kind", "external_id", name="uq_source_item_kind_external"),
    )

    id: int | None = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=_now)


class Draft(SQLModel, table=True):
    """A generated post awaiting review.

    The row is inserted *before* generation starts, so it doubles as the job
    record: that is why progress lives here and there is no event table.
    """

    __tablename__ = "draft"

    id: int | None = Field(default=None, primary_key=True)
    page_id: int = Field(foreign_key="page.id", index=True)
    source_item_id: int | None = Field(
        default=None, foreign_key="source_item.id", index=True
    )
    """Null means the draft came from a topic rather than a Source Item."""

    topic: str | None = None
    status: DraftStatus = Field(
        default=DraftStatus.GENERATING, index=True, sa_type=_stored_enum(DraftStatus)
    )


    hook: str | None = None
    """The text on the image panel. Also the only text a brand rule guards.

    `overlay_text` used to sit beside this, holding the same string — the writer
    filled both from prompts that gave them identical rules. It was dropped on
    2026-08-06 because the split had a cost and no benefit: validation ran here
    and the compositor drew the other one.
    """

    caption: str | None = None
    first_comment: str | None = None
    highlight_phrases: list[str] = Field(default_factory=list, sa_column=Column(JSON))

    hashtags: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    """**Dead as of 2026-08-12 (feedback E1, reversed). Nothing writes this.**

    Kept, not dropped, because 20 of 21 drafts carry values and a dropped column
    has no undo — one of them is already in Metricool's planner with its tags in
    the published text, which is the only record of what that post actually says.
    The writer no longer produces them, `_post_text` no longer appends them, and
    the web app no longer shows the field; new drafts get the empty default.

    Reading it is still fine. `schedule-list.tsx` parses tags back out of planner
    *text* for the 302 posts the old system queued, and that is unrelated to this
    column.
    """

    image_prompt: str | None = None

    template: str | None = None
    """`card` or `full_overlay` for this draft alone. Null takes the Page's.

    The same contract every other per-draft override has: null means "whatever
    the Page is set to" and follows it when that changes, so a draft that has
    chosen nothing is not quietly pinned to today's value.

    Per draft because the client asked to switch a post between the two forms
    at review, and the choice depends on the picture — a busy photograph with a
    face in the lower third is ruined by a panel lying over it, and the same
    panel is the making of a wide landscape.

    A string rather than an enum for the same reason `_stored_enum` exists at
    all: the set of templates is a fact about the compositor, and `Layout`
    validates it on the way through (`layout_for.resolve_draft`).
    """

    no_image: bool = Field(default=False)
    """Publish this as text only — no hero, no card, no picture at all.

    A column rather than "the composite happens to be missing", because those
    are different states and only one of them is publishable. A draft whose
    image generation *failed* has an empty `composed_image_path` and a warning,
    and must not go out; this one has an empty `composed_image_path` on purpose.

    `build_image` is skipped entirely on a run that sets it, so it is also the
    only generate path that costs nothing at all.
    """

    hero_from_source: bool = Field(default=False)
    """Take the hero from the Source Item's own picture instead of buying one.

    A column rather than a decision made at draw time, because a rebuild has to
    take the same path the run did. Derived from "does the source have an
    image_url" it would flip on its own — a feed that starts or stops carrying
    pictures would silently change what a rebuild costs and what the card looks
    like.

    False is the default and means the Gemini call. `image_prompt` stays
    populated either way: the writer produced it, it costs nothing to keep, and
    it is what a later "buy one after all" would use.
    """

    hero_image_path: str | None = None
    composed_image_path: str | None = None
    """Kept apart so re-compositing an edit does not re-pay for image generation."""

    inset_image_path: str | None = None
    """The circular inset: a picture the operator uploaded, cropped to a disc.

    Null is the normal case — no upload, no circle, and the card is the one it
    was before. Nothing generates this: it is the one image in the app that
    comes from a person rather than a model, which is why there is no prompt
    column beside it.
    """

    inset_size_px: int | None = None
    """Diameter of the disc. Null takes `layout.portrait.size_px`.

    Per-draft because it is the one thing about the inset that depends on the
    picture in it: a head-and-shoulders portrait reads at 140px and a wide
    photograph of two people does not. Clamped on write — see
    `Layout.portrait.clamp`.
    """

    inset_border_width_px: int | None = None
    """Ring thickness. Null takes `layout.portrait.border_width_px`; 0 is no ring.

    Per draft for the same reason the diameter is: the right ring depends on the
    picture in the disc, not on the brand. A dark portrait wants a light ring to
    separate it from the panel; a bright one usually wants none at all. Null and
    0 are different answers — null tracks whatever the Page is set to, 0 is this
    draft choosing to have no ring.
    """

    inset_border_color: str | None = None
    """Ring colour. Null takes `layout.portrait.border_color`.

    The Page's default is black, which reads as a cut-out where the ring crosses
    the panel. That is the right default and the wrong answer for a picture that
    is itself mostly black, which is what this column is for.
    """

    inset_x_ratio: float | None = None
    inset_y_ratio: float | None = None
    """Centre of the disc, as fractions of card width and height. Null is the seam.

    Ratios rather than pixels, which is what the old app stored
    (`centerXRatio`/`centerYRatio`) and is the only thing that survives the card
    changing size. **Null is not 0** — it means "wherever the default is", and
    the default cannot be written down as a number here because the seam moves:
    the panel grows with the copy, so `hero_height_px` is different for every
    draft. `compositor.compose` resolves it at draw time.
    """

    warnings: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    """Brand rules still failing after the writer exhausted its retries."""

    metricool_post_id: str | None = Field(default=None, index=True)
    """What Metricool called the post it queued. The whole of our publish state.

    There is no `scheduled_at` beside it, and that is ADR-0001 rather than an
    omission: the old system mirrored every scheduled post into a table with a
    five-value status enum, a due-post cron and a stale-`PROCESSING` recovery
    path, and production held **0 rows against 237 approved drafts**. Metricool's
    planner is the source of truth for when a post goes out; this column exists
    only so we can ask it about ours.
    """

    progress_step: str | None = None
    progress_pct: int = 0
    error: str | None = None

    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)

    # Serialised, never stored. The columns above hold a path relative to the
    # bucket; these are where that path resolves to right now.
    #
    # The split is what keeps a row portable. A stored URL welds every draft to
    # one Supabase project and one bucket name, so changing either — a new
    # project, a rename, a different region — becomes an UPDATE across the table
    # instead of an env var. It is also what lets dev and production differ by
    # one config line rather than by two sets of rows that cannot be swapped.
    #
    # Built here rather than in React, which is where the old app built it
    # (`social-agent/src/lib/facebook/media-url.ts`, from
    # `NEXT_PUBLIC_SUPABASE_URL` plus a hardcoded bucket constant). One place
    # knows what a bucket is.

    @computed_field  # type: ignore[prop-decorator]
    @property
    def hero_image_url(self) -> str | None:
        return media.public_url(self.hero_image_path) if self.hero_image_path else None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def composed_image_url(self) -> str | None:
        return (
            media.public_url(self.composed_image_path)
            if self.composed_image_path
            else None
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def inset_image_url(self) -> str | None:
        return (
            media.public_url(self.inset_image_path) if self.inset_image_path else None
        )
