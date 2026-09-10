"""prompt_template page_id not null

Every style is one Page's (client, 2026-09-11): History Retraced was offered
Bodybuilding's "Workout Infographic" through the null-global contract, so null
is no longer a legal state. The one legacy row is assigned to the Page its
content was written for — its image brief is a muscular-male fitness
infographic — before the column tightens, because SET NOT NULL against a null
row would fail.

Revision ID: 4c88d1d59926
Revises: d1ab74d861bc
Create Date: 2026-09-11 00:45:49.798401

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
# SQLModel's own column types (AutoString) are rendered into these files by
# autogenerate, so the import has to be here even when a revision does not use it.
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '4c88d1d59926'
down_revision: Union[str, Sequence[str], None] = 'd1ab74d861bc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Data before shape: any row the column caught null gets the Page its
    # content names. The live database holds exactly one such row (Workout
    # Infographic); a fresh database has none and the UPDATE is a no-op.
    op.execute(
        "UPDATE prompt_template SET page_id = ("
        "SELECT min(id) FROM page WHERE name ILIKE 'bodybuilding%')"
        " WHERE page_id IS NULL"
    )
    op.alter_column(
        "prompt_template", "page_id", existing_type=sa.Integer(), nullable=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column(
        "prompt_template", "page_id", existing_type=sa.Integer(), nullable=True
    )