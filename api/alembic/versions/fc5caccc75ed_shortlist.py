"""shortlist

The Shortlisted tab's stored list, one row per Page, and two Page settings:
how many it keeps and when the day's list is made. Existing Pages get the
model's default time, 06:00, so every Page has a daily list.

Revision ID: fc5caccc75ed
Revises: a7c2e4f19b30
Create Date: 2026-10-28 21:44:39.857255

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
# SQLModel's own column types (AutoString) are rendered into these files by
# autogenerate, so the import has to be here even when a revision does not use it.
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'fc5caccc75ed'
down_revision: Union[str, Sequence[str], None] = 'a7c2e4f19b30'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('shortlist',
    sa.Column('page_id', sa.Integer(), nullable=False),
    sa.Column('made_at', sa.DateTime(), nullable=False),
    sa.Column('considered', sa.Integer(), nullable=False),
    sa.Column('failed_feeds', sa.Integer(), nullable=False),
    sa.Column('items', sa.JSON(), nullable=False),
    sa.ForeignKeyConstraint(['page_id'], ['page.id'], ),
    sa.PrimaryKeyConstraint('page_id')
    )
    op.add_column('page', sa.Column('shortlist_size', sa.Integer(), server_default='10', nullable=False))
    op.add_column('page', sa.Column('shortlist_minute', sa.Integer(), nullable=True))
    op.execute("UPDATE page SET shortlist_minute = 360")


def downgrade() -> None:
    op.drop_column('page', 'shortlist_minute')
    op.drop_column('page', 'shortlist_size')
    op.drop_table('shortlist')
