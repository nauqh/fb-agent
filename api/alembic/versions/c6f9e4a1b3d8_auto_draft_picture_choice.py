"""page auto_draft_picture replaces auto_draft_images

Revision ID: c6f9e4a1b3d8
Revises: b5e8d3f0a2c7
Create Date: 2026-10-07 15:40:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c6f9e4a1b3d8"
down_revision: Union[str, Sequence[str], None] = "b5e8d3f0a2c7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """A switch that was off stays text-only; one that was on takes Google."""
    op.add_column(
        "page",
        sa.Column("auto_draft_picture", sa.String(), nullable=False, server_default="google"),
    )
    op.execute("UPDATE page SET auto_draft_picture = 'none' WHERE NOT auto_draft_images")
    op.drop_column("page", "auto_draft_images")


def downgrade() -> None:
    op.add_column(
        "page",
        sa.Column("auto_draft_images", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.execute("UPDATE page SET auto_draft_images = false WHERE auto_draft_picture = 'none'")
    op.drop_column("page", "auto_draft_picture")
