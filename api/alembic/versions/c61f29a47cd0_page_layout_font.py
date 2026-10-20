"""page layout font

Revision ID: c61f29a47cd0
Revises: c6e9f2a5b8d3
Create Date: 2026-10-20 19:16:18.295097

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
# SQLModel's own column types (AutoString) are rendered into these files by
# autogenerate, so the import has to be here even when a revision does not use it.
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'c61f29a47cd0'
down_revision: Union[str, Sequence[str], None] = 'c6e9f2a5b8d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """A Page's font pick. Null tracks layout.yml."""
    op.add_column('page_layout', sa.Column('font', sqlmodel.sql.sqltypes.AutoString(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('page_layout', 'font')
