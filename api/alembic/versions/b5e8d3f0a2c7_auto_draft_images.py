"""page auto_draft_images and draft hero_search

Revision ID: b5e8d3f0a2c7
Revises: a4f7c2e9d1b3
Create Date: 2026-10-07 15:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b5e8d3f0a2c7"
down_revision: Union[str, Sequence[str], None] = "a4f7c2e9d1b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Server defaults so existing rows fill: every Page keeps pictures on."""
    op.add_column(
        "page",
        sa.Column("auto_draft_images", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "draft",
        sa.Column("hero_search", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("draft", "hero_search")
    op.drop_column("page", "auto_draft_images")
