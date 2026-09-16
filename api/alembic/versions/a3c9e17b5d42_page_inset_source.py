"""page and draft inset_source: where the inset search looks

Revision ID: a3c9e17b5d42
Revises: 7b2e4c91d0a3
Create Date: 2026-09-16 19:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
# SQLModel's own column types (AutoString) are rendered into these files by
# autogenerate, so the import has to be here even when a revision does not use it.
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'a3c9e17b5d42'
down_revision: Union[str, Sequence[str], None] = '7b2e4c91d0a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Additive, and every existing Page starts on 'google' - what the inset
    # search already does - so nothing changes until an operator picks Unsplash.
    # The server default is for the reason `find_inset` keeps its own in
    # 1a3d0b07d12b: production's older code omits the column on INSERT during a
    # deploy against the shared Postgres.
    op.add_column(
        'page',
        sa.Column(
            'inset_source',
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=False,
            server_default='google',
        ),
    )
    # A run's own override, chosen beside Find inset. Null is "use the Page's",
    # which is every existing draft and every run that did not touch it.
    op.add_column(
        'draft',
        sa.Column('inset_source', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('draft', 'inset_source')
    op.drop_column('page', 'inset_source')
