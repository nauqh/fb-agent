"""website articles: the full RSS text, and the article beside the post

Revision ID: e8b3c6d9f2a5
Revises: d7a2f5c8e1b4
Create Date: 2026-10-10 14:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e8b3c6d9f2a5"
down_revision: Union[str, Sequence[str], None] = "d7a2f5c8e1b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("source_item", sa.Column("body", sa.Text(), nullable=True))
    op.add_column(
        "draft", sa.Column("article_title", sqlmodel.sql.sqltypes.AutoString(), nullable=True)
    )
    op.add_column("draft", sa.Column("article_html", sa.Text(), nullable=True))
    op.add_column(
        "draft", sa.Column("article_url", sqlmodel.sql.sqltypes.AutoString(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("draft", "article_url")
    op.drop_column("draft", "article_html")
    op.drop_column("draft", "article_title")
    op.drop_column("source_item", "body")
