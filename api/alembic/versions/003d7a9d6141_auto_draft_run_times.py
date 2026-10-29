"""auto draft run times

Per-Page times for the automatic drafts. Existing Pages keep the old behaviour:
one run at 06:00 in the Page's zone.

Revision ID: 003d7a9d6141
Revises: afa53713faeb
Create Date: 2026-10-29 16:03:33.341157

"""
from typing import Sequence, Union

import sqlalchemy as sa

# SQLModel's own column types (AutoString) are rendered into these files by
# autogenerate, so the import has to be here even when a revision does not use it.
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '003d7a9d6141'
down_revision: Union[str, Sequence[str], None] = 'afa53713faeb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'page_auto_draft_time',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('page_id', sa.Integer(), nullable=False),
        sa.Column('minute_of_day', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['page_id'], ['page.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'page_id', 'minute_of_day', name='uq_auto_draft_time_page_minute'
        ),
    )
    op.create_index(
        op.f('ix_page_auto_draft_time_minute_of_day'),
        'page_auto_draft_time',
        ['minute_of_day'],
        unique=False,
    )
    op.create_index(
        op.f('ix_page_auto_draft_time_page_id'),
        'page_auto_draft_time',
        ['page_id'],
        unique=False,
    )

    # The cron used to fire once at 06:00 for every Page. Seed that time so no
    # Page silently stops drafting when this ships.
    op.execute(
        "INSERT INTO page_auto_draft_time (page_id, minute_of_day, created_at) "
        "SELECT id, 360, NOW() FROM page"
    )


def downgrade() -> None:
    op.drop_index(
        op.f('ix_page_auto_draft_time_page_id'), table_name='page_auto_draft_time'
    )
    op.drop_index(
        op.f('ix_page_auto_draft_time_minute_of_day'), table_name='page_auto_draft_time'
    )
    op.drop_table('page_auto_draft_time')
