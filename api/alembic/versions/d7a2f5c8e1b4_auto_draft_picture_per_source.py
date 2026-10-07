"""page picture choice per auto-draft source

Revision ID: d7a2f5c8e1b4
Revises: c6f9e4a1b3d8
Create Date: 2026-10-07 16:30:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d7a2f5c8e1b4"
down_revision: Union[str, Sequence[str], None] = "c6f9e4a1b3d8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Every Page keeps what it had for both sources. A competitor `source`,
    which only ever produced no picture, becomes `none`."""
    op.alter_column("page", "auto_draft_picture", new_column_name="auto_draft_competitor_picture")
    op.add_column(
        "page",
        sa.Column("auto_draft_rss_picture", sa.String(), nullable=False, server_default="source"),
    )
    op.execute("UPDATE page SET auto_draft_rss_picture = auto_draft_competitor_picture")
    op.execute(
        "UPDATE page SET auto_draft_competitor_picture = 'none' "
        "WHERE auto_draft_competitor_picture = 'source'"
    )


def downgrade() -> None:
    op.drop_column("page", "auto_draft_rss_picture")
    op.alter_column("page", "auto_draft_competitor_picture", new_column_name="auto_draft_picture")
