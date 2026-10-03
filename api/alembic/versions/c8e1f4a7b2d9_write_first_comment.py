"""page and post style write_first_comment

Revision ID: c8e1f4a7b2d9
Revises: b7d2e4f19a60
Create Date: 2026-10-03 13:40:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c8e1f4a7b2d9"
down_revision: Union[str, Sequence[str], None] = "b7d2e4f19a60"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Additive and null: every Page and style keeps writing a first comment."""
    op.add_column("page", sa.Column("write_first_comment", sa.Boolean(), nullable=True))
    op.add_column(
        "prompt_template", sa.Column("write_first_comment", sa.Boolean(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("prompt_template", "write_first_comment")
    op.drop_column("page", "write_first_comment")
