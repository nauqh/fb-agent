"""page and saved_post: automatic save and repost

Revision ID: c4f1a8e20b67
Revises: a3c9e17b5d42
Create Date: 2026-09-17 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
# SQLModel's own column types (AutoString) are rendered into these files by
# autogenerate, so the import has to be here even when a revision does not use it.
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'c4f1a8e20b67'
down_revision: Union[str, Sequence[str], None] = 'a3c9e17b5d42'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Additive, all off: null thresholds on every Page, and every existing saved
    # post was saved by hand. `auto_saved` carries a server default for the
    # reason 1a3d0b07d12b gives - production's older code omits the column on
    # INSERT during a deploy against the shared Postgres.
    op.add_column('page', sa.Column('auto_save_min_reactions', sa.Integer(), nullable=True))
    op.add_column('page', sa.Column('auto_repost_after_days', sa.Integer(), nullable=True))
    op.add_column(
        'saved_post',
        sa.Column('auto_saved', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column('saved_post', sa.Column('repost_draft_id', sa.Integer(), nullable=True))
    op.add_column(
        'saved_post',
        sa.Column('repost_error', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    )
    op.add_column('saved_post', sa.Column('dismissed_at', sa.DateTime(), nullable=True))
    op.create_foreign_key(
        None, 'saved_post', 'draft', ['repost_draft_id'], ['id'], ondelete='SET NULL'
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        'saved_post_repost_draft_id_fkey', 'saved_post', type_='foreignkey'
    )
    op.drop_column('saved_post', 'dismissed_at')
    op.drop_column('saved_post', 'repost_error')
    op.drop_column('saved_post', 'repost_draft_id')
    op.drop_column('saved_post', 'auto_saved')
    op.drop_column('page', 'auto_repost_after_days')
    op.drop_column('page', 'auto_save_min_reactions')
