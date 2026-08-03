"""The three tables. See docs/data-model.md for why there are only three.

Nothing here carries a user_id (ADR-0002), a brand_key (ADR-0003), or any
schedule state (ADR-0001). Layout lives in config/layout.yml, not on Page.
"""

from datetime import datetime, timezone
from enum import StrEnum

from sqlmodel import JSON, Column, Field, SQLModel, UniqueConstraint


def _now() -> datetime:
    return datetime.now(timezone.utc)


class SourceKind(StrEnum):
    RIVAL_POST = "rival_post"
    TWEET = "tweet"
    ARTICLE = "article"

    @property
    def is_factual(self) -> bool:
        """Whether the *subject* binds the writer.

        A rival post is borrowed for tone only; a tweet or article must produce
        a post about that same story. Reversing this tells the model to treat a
        Smithsonian article as a writing sample. Derived, never stored — a
        stored copy is a second truth, and when it drifts the model still
        returns confident, well-formed output about the wrong story.
        """
        return self is not SourceKind.RIVAL_POST


class DraftStatus(StrEnum):
    GENERATING = "generating"
    REVIEW = "review"
    APPROVED = "approved"
    REJECTED = "rejected"


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

    daily_quota: int = 12
    """Posts per calendar day in Asia/Ho_Chi_Minh."""

    watermark_image_path: str | None = None
    """The page's own logo, relative to media_root.

    Null for History Retraced, and that is not a gap: both Supabase Storage
    objects the old rows referenced return `NoSuchKey`, and the newest composite
    in that bucket renders "History Retraced" as white text top-right. The text
    fallback is what production ships.
    """

    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


class SourceItem(SQLModel, table=True):
    """External material selected as input. One table, three kinds."""

    __tablename__ = "source_item"
    __table_args__ = (
        # Ticking the same article twice must not create a second row.
        UniqueConstraint("kind", "external_id", name="uq_source_item_kind_external"),
    )

    id: int | None = Field(default=None, primary_key=True)
    kind: SourceKind = Field(index=True)
    external_id: str
    author: str | None = None
    """Rival page name, X handle, or publisher."""

    synced_for_page_id: int | None = Field(
        default=None, foreign_key="page.id", index=True
    )
    """Whose competitor set this belongs to. rival_post only."""

    text: str = ""
    url: str | None = None
    image_url: str | None = None
    published_at: datetime | None = None

    reactions: int | None = None
    comments: int | None = None
    shares: int | None = None
    """Null for tweets and articles. Reactions is the default sort on Rivals."""

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
    status: DraftStatus = Field(default=DraftStatus.GENERATING, index=True)

    hook: str | None = None
    caption: str | None = None
    first_comment: str | None = None
    overlay_text: str | None = None
    highlight_phrases: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    hashtags: list[str] = Field(default_factory=list, sa_column=Column(JSON))

    image_prompt: str | None = None
    hero_image_path: str | None = None
    composed_image_path: str | None = None
    """Kept apart so re-compositing an edit does not re-pay for image generation."""

    warnings: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    """Brand rules still failing after the writer exhausted its retries."""

    progress_step: str | None = None
    progress_pct: int = 0
    error: str | None = None

    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)
