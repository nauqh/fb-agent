"""quote marks and attribution

Two per-draft quote card settings: whether the quotation marks are drawn, and
who said it.

A quote form's `page_layout.font` now names a quote face (`QUOTE_FONTS`). The
quote rows that exist were copied from each Page's card row by 9f42a0cdb943,
so their fonts are card faces nobody picked for a quote. They are cleared.

Revision ID: a7c2e4f19b30
Revises: 9f42a0cdb943
Create Date: 2026-10-25 01:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
# SQLModel's own column types (AutoString) are rendered into these files by
# autogenerate, so the import has to be here even when a revision does not use it.
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'a7c2e4f19b30'
down_revision: Union[str, Sequence[str], None] = '9f42a0cdb943'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "draft",
        sa.Column("quote_marks", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.alter_column("draft", "quote_marks", server_default=None)
    op.add_column(
        "draft", sa.Column("attribution", sqlmodel.sql.sqltypes.AutoString(), nullable=True)
    )
    op.execute("UPDATE page_layout SET font = NULL WHERE form = 'quote'")


def downgrade() -> None:
    op.drop_column("draft", "attribution")
    op.drop_column("draft", "quote_marks")
