"""website articles: the call to action, and an article prompt per Page and style

Revision ID: a4c7e2b9d1f3
Revises: e8b3c6d9f2a5
Create Date: 2026-10-12 17:30:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a4c7e2b9d1f3"
down_revision: Union[str, Sequence[str], None] = "e8b3c6d9f2a5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("page", sa.Column("article_prompt", sa.Text(), nullable=True))
    op.add_column(
        "page", sa.Column("article_cta", sqlmodel.sql.sqltypes.AutoString(), nullable=True)
    )
    op.add_column("prompt_template", sa.Column("article_prompt", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("prompt_template", "article_prompt")
    op.drop_column("page", "article_cta")
    op.drop_column("page", "article_prompt")
