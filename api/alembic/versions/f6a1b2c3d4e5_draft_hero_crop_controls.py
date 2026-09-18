"""draft hero crop controls

Revision ID: f6a1b2c3d4e5
Revises: c4f1a8e20b67
Create Date: 2026-09-18 22:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f6a1b2c3d4e5"
down_revision: Union[str, Sequence[str], None] = "c4f1a8e20b67"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Store the crop used for the hero in the preview and composite."""
    op.add_column(
        "draft",
        sa.Column("hero_x_ratio", sa.Float(), nullable=False, server_default="0.5"),
    )
    op.add_column(
        "draft",
        sa.Column("hero_y_ratio", sa.Float(), nullable=False, server_default="0.5"),
    )
    op.add_column(
        "draft",
        sa.Column("hero_zoom", sa.Float(), nullable=False, server_default="1.0"),
    )


def downgrade() -> None:
    """Remove the saved crop controls."""
    op.drop_column("draft", "hero_zoom")
    op.drop_column("draft", "hero_y_ratio")
    op.drop_column("draft", "hero_x_ratio")
