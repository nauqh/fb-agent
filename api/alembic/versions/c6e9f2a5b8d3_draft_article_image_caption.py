"""draft article image caption: under the featured image on the website

Revision ID: c6e9f2a5b8d3
Revises: b5d8e1f4a7c2
Create Date: 2026-10-13 02:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c6e9f2a5b8d3"
down_revision: Union[str, Sequence[str], None] = "b5d8e1f4a7c2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "draft",
        sa.Column("article_image_caption", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("draft", "article_image_caption")
