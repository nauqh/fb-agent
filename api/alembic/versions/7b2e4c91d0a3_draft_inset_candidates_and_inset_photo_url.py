"""draft inset_candidates and inset_photo_url: a find's alternatives, kept

Revision ID: 7b2e4c91d0a3
Revises: 1a3d0b07d12b
Create Date: 2026-09-15 04:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
# SQLModel's own column types (AutoString) are rendered into these files by
# autogenerate, so the import has to be here even when a revision does not use it.
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '7b2e4c91d0a3'
down_revision: Union[str, Sequence[str], None] = '1a3d0b07d12b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Additive, so existing drafts are kept. The server default stays for the
    # reason `find_inset` keeps its own in 1a3d0b07d12b: dev and production
    # share one Postgres, production's older code omits this column on INSERT
    # during a deploy, and a null list would fail the API's response validation.
    op.add_column(
        'draft',
        sa.Column('inset_candidates', sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )
    op.add_column('draft', sa.Column('inset_photo_url', sqlmodel.sql.sqltypes.AutoString(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('draft', 'inset_photo_url')
    op.drop_column('draft', 'inset_candidates')
