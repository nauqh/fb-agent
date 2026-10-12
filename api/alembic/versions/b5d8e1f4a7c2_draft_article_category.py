"""draft article category: the WordPress category the article is filed under

Revision ID: b5d8e1f4a7c2
Revises: a4c7e2b9d1f3
Create Date: 2026-10-13 01:10:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b5d8e1f4a7c2"
down_revision: Union[str, Sequence[str], None] = "a4c7e2b9d1f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("draft", sa.Column("article_category_id", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("draft", "article_category_id")
