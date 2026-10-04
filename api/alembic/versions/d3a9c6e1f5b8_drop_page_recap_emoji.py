"""drop page recap_emoji

Revision ID: d3a9c6e1f5b8
Revises: c8e1f4a7b2d9
Create Date: 2026-10-05 00:30:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d3a9c6e1f5b8"
down_revision: Union[str, Sequence[str], None] = "c8e1f4a7b2d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """The caption emoji is the Page's prompt's call now, not a setting."""
    op.drop_column("page", "recap_emoji")


def downgrade() -> None:
    op.add_column("page", sa.Column("recap_emoji", sa.Boolean(), nullable=True))
