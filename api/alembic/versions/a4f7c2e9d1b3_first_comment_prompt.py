"""page and post style first_comment_prompt

Revision ID: a4f7c2e9d1b3
Revises: d3a9c6e1f5b8
Create Date: 2026-10-07 13:30:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a4f7c2e9d1b3"
down_revision: Union[str, Sequence[str], None] = "d3a9c6e1f5b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Additive and null: every Page and style inherits `first_comment.txt`."""
    op.add_column("page", sa.Column("first_comment_prompt", sa.Text(), nullable=True))
    op.add_column(
        "prompt_template", sa.Column("first_comment_prompt", sa.Text(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("prompt_template", "first_comment_prompt")
    op.drop_column("page", "first_comment_prompt")
