"""draft text size

A per-draft font size for the overlay, set on the review page. Null keeps
following the Page's.

Revision ID: afa53713faeb
Revises: fc5caccc75ed
Create Date: 2026-10-29 03:40:26.725638

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
# SQLModel's own column types (AutoString) are rendered into these files by
# autogenerate, so the import has to be here even when a revision does not use it.
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'afa53713faeb'
down_revision: Union[str, Sequence[str], None] = 'fc5caccc75ed'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('draft', sa.Column('text_size_px', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('draft', 'text_size_px')
