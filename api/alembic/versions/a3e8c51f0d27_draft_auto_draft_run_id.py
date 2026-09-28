"""draft auto draft run id

Revision ID: a3e8c51f0d27
Revises: c1a7f30de845
Create Date: 2026-09-28 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a3e8c51f0d27"
down_revision: Union[str, Sequence[str], None] = "c1a7f30de845"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Say which drafts the automation wrote, so Review can tell them apart."""
    op.add_column("draft", sa.Column("auto_draft_run_id", sa.Integer(), nullable=True))
    op.create_index(
        op.f("ix_draft_auto_draft_run_id"), "draft", ["auto_draft_run_id"], unique=False
    )
    op.create_foreign_key(
        "draft_auto_draft_run_id_fkey",
        "draft",
        "auto_draft_run",
        ["auto_draft_run_id"],
        ["id"],
    )
    # A run records its row just after `start_run` commits its drafts, so the
    # drafts a run made are its Page's, dated in the minute before it.
    op.execute(
        """
        UPDATE draft SET auto_draft_run_id = run.id
        FROM auto_draft_run AS run
        WHERE run.drafts_created > 0
          AND draft.page_id = run.page_id
          AND draft.source_item_id IS NOT NULL
          AND draft.created_at <= run.created_at
          AND draft.created_at > run.created_at - INTERVAL '1 minute'
        """
    )


def downgrade() -> None:
    op.drop_constraint("draft_auto_draft_run_id_fkey", "draft", type_="foreignkey")
    op.drop_index(op.f("ix_draft_auto_draft_run_id"), table_name="draft")
    op.drop_column("draft", "auto_draft_run_id")
