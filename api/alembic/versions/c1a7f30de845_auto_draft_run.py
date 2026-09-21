"""auto draft run

Revision ID: c1a7f30de845
Revises: b7d4e9a12c30
Create Date: 2026-09-21 01:10:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c1a7f30de845"
down_revision: Union[str, Sequence[str], None] = "b7d4e9a12c30"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Record every auto-draft run, including the ones that made nothing.

    The Draft rows cannot answer "did tonight's run fire": a run that generated
    nothing leaves no trace on them, and one that generated two is
    indistinguishable from an operator pressing Generate twice.
    """
    op.create_table(
        "auto_draft_run",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("page_id", sa.Integer(), nullable=False),
        sa.Column("drafts_created", sa.Integer(), nullable=False),
        sa.Column("available", sa.Integer(), nullable=False),
        sa.Column("note", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["page_id"], ["page.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_auto_draft_run_page_id"), "auto_draft_run", ["page_id"], unique=False
    )
    # The monitor reads newest-first across every Page and nothing else, so the
    # ordering column is the one that earns an index.
    op.create_index(
        op.f("ix_auto_draft_run_created_at"),
        "auto_draft_run",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    """Drop the run history. Nothing reads it back to decide what to do next."""
    op.drop_index(op.f("ix_auto_draft_run_created_at"), table_name="auto_draft_run")
    op.drop_index(op.f("ix_auto_draft_run_page_id"), table_name="auto_draft_run")
    op.drop_table("auto_draft_run")
