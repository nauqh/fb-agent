"""page: per-page caption limits

Revision ID: b7d4e9a12c30
Revises: f6a1b2c3d4e5
Create Date: 2026-09-19 23:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
# SQLModel's own column types (AutoString) are rendered into these files by
# autogenerate, so the import has to be here even when a revision does not use it.
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'b7d4e9a12c30'
down_revision: Union[str, Sequence[str], None] = 'f6a1b2c3d4e5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Additive and null on every existing Page, which is the house rule: five
    # points, each opening with an emoji. Nullable rather than defaulted for
    # the reason the other length columns give - a copied default cannot be
    # told from a chosen one. `recap_emoji` is deliberately not given a server
    # default either: false is the only override worth storing, and a NOT NULL
    # true would erase the difference between choosing the rule and never
    # looking at it.
    op.add_column('page', sa.Column('recap_max_points', sa.Integer(), nullable=True))
    op.add_column('page', sa.Column('recap_emoji', sa.Boolean(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('page', 'recap_emoji')
    op.drop_column('page', 'recap_max_points')
