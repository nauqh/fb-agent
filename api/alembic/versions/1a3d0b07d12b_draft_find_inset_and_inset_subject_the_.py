"""draft find_inset and inset_subject: the inset found by the AI

Revision ID: 1a3d0b07d12b
Revises: 4c88d1d59926
Create Date: 2026-09-14 17:35:31.106072

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
# SQLModel's own column types (AutoString) are rendered into these files by
# autogenerate, so the import has to be here even when a revision does not use it.
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '1a3d0b07d12b'
down_revision: Union[str, Sequence[str], None] = '4c88d1d59926'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Additive, so existing drafts are kept. The server default is **kept**,
    # unlike `9a8d2213232a` for `no_image`: dev and production share one
    # Postgres, so this can land before production runs the code that knows the
    # column. Production's older `Draft` omits `find_inset` on INSERT, and a
    # NOT NULL column with no default would fail every draft it creates.
    op.add_column(
        'draft',
        sa.Column('find_inset', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column('draft', sa.Column('inset_subject', sqlmodel.sql.sqltypes.AutoString(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('draft', 'inset_subject')
    op.drop_column('draft', 'find_inset')
