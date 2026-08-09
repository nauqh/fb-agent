"""The three tables. See docs/data-model.md for why there are only three.

Nothing here carries a user_id (ADR-0002), a brand_key (ADR-0003), or any
schedule state (ADR-0001). Layout lives in config/layout.yml, not on Page.
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
    - **Adding a value must not need a migration.** A native enum makes it an
      `ALTER TYPE`, which `create_all` will never perform, in a repo that has
      deliberately chosen to run no migration tool. `create_constraint` is left
      off for the same reason — a `CHECK` would need altering too.
    - **It must load back as the enum, not as `str`.** `sa_type=String` gets the
      first two and silently loses this one: `SourceKind.is_factual` is a
      property, `sources/__init__.py` asks for it on a value read from the
      database, and a bare string raises `AttributeError` mid-run. The tests did
      not catch it — they construct their rows rather than reloading them — so
      it would have shipped.

    `length` is fixed rather than derived. SQLAlchemy sizes the column to the
    longest *current* value, so a longer member added later silently needs an
    `ALTER TABLE` on Postgres; 32 is clear of every value either enum has.
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

    created_at: datetime = Field(default_factory=_now)
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
    """Whose competitor set this belongs to. competitor_post only."""

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

    image_prompt: str | None = None
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
