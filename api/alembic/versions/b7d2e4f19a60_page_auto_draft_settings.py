"""page auto-draft settings, and which source each run drew from

Revision ID: b7d2e4f19a60
Revises: a3e8c51f0d27
Create Date: 2026-09-29 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b7d2e4f19a60"
down_revision: Union[str, Sequence[str], None] = "a3e8c51f0d27"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Additive, all off, except the one Page the cron already ran for."""
    op.add_column("page", sa.Column("auto_draft_competitor_count", sa.Integer(), nullable=True))
    op.add_column(
        "page", sa.Column("auto_draft_competitor_min_reactions", sa.Integer(), nullable=True)
    )
    op.add_column("page", sa.Column("auto_draft_rss_count", sa.Integer(), nullable=True))
    op.add_column("page", sa.Column("auto_draft_rss_instructions", sa.Text(), nullable=True))
    # Every run so far drew from competitors. The server default also covers
    # the old code inserting runs during the deploy.
    op.add_column(
        "auto_draft_run",
        sa.Column(
            "source",
            sa.Enum(
                "competitor_post", "tweet", "rss", "web",
                name="sourcekind", native_enum=False, length=32,
            ),
            nullable=False,
            server_default="competitor_post",
        ),
    )
    # The workflow's PAGE_IDS was "2" and TARGET 2. Carried over so the switch
    # to Settings changes nothing on the night it deploys.
    op.execute("UPDATE page SET auto_draft_competitor_count = 2 WHERE id = 2")


def downgrade() -> None:
    op.drop_column("auto_draft_run", "source")
    op.drop_column("page", "auto_draft_rss_instructions")
    op.drop_column("page", "auto_draft_rss_count")
    op.drop_column("page", "auto_draft_competitor_min_reactions")
    op.drop_column("page", "auto_draft_competitor_count")
