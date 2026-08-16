"""Per-Page writing lengths and prompt overrides

Revision ID: e232c1fcb279
Revises: 517b138512ff
Create Date: 2026-08-17 04:21:22.429076

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
# SQLModel's own column types (AutoString) are rendered into these files by
# autogenerate, so the import has to be here even when a revision does not use it.
import sqlmodel  # noqa: F401


# revision identifiers, used by Alembic.
revision: str = 'e232c1fcb279'
down_revision: Union[str, Sequence[str], None] = '517b138512ff'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    All eight are nullable, and null is load-bearing rather than merely
    convenient: it means "inherit". The lengths fall back to the house numbers
    in `writer/validators.py`, and the prompts to `prompts/pages/<slug>/x.txt`
    or the global file. Defaulting any of them would copy today's value onto
    every Page, and a copied default cannot be told from a chosen one — which
    is the drift these columns are shaped to avoid.

    The three prompt columns are `TEXT`, not autogenerate's unbounded
    `VARCHAR`. Same storage in Postgres; the point is that a reader of this file
    can see these hold multi-kilobyte prose rather than a short string.
    """
    op.add_column('page', sa.Column('hook_max_words', sa.Integer(), nullable=True))
    op.add_column('page', sa.Column('first_comment_min_chars', sa.Integer(), nullable=True))
    op.add_column('page', sa.Column('first_comment_max_chars', sa.Integer(), nullable=True))
    op.add_column('page', sa.Column('first_comment_min_paragraphs', sa.Integer(), nullable=True))
    op.add_column('page', sa.Column('first_comment_max_paragraphs', sa.Integer(), nullable=True))
    op.add_column('page', sa.Column('system_prompt', sa.Text(), nullable=True))
    op.add_column('page', sa.Column('overlay_prompt', sa.Text(), nullable=True))
    op.add_column('page', sa.Column('image_prompt', sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema. Drops any prompt an operator has written — it lives
    nowhere else, unlike the files, which are in git."""
    op.drop_column('page', 'image_prompt')
    op.drop_column('page', 'overlay_prompt')
    op.drop_column('page', 'system_prompt')
    op.drop_column('page', 'first_comment_max_paragraphs')
    op.drop_column('page', 'first_comment_min_paragraphs')
    op.drop_column('page', 'first_comment_max_chars')
    op.drop_column('page', 'first_comment_min_chars')
    op.drop_column('page', 'hook_max_words')
    # ### end Alembic commands ###
