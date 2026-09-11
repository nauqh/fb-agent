"""prompt_template: named post styles, selectable at run time

The client's request (2026-08-20): on the prompts screen, create named prompt
templates, each with its own system/overlay/image text, and pick one on the
generate screen. The table stores **deltas only** - every prompt column is
nullable and blank inherits the Page's chain - because full copies are the
measured drift failure this repo's prompt layout was built against.

`draft.prompt_template_id` records the style a draft was generated under so a
regenerate or hero rebuild uses the same voice rather than the operator's
current dropdown.

Hand-written like the rest: the live database is the only Postgres and the
shape is small (see 77c12e0f0a01 for the convention). No `created_at` -
nothing displays or sorts on it.

Revision ID: a3f8c2d91b47
Revises: 77c12e0f0a01
Create Date: 2026-08-21

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "a3f8c2d91b47"
down_revision: Union[str, None] = "77c12e0f0a01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # The live database already carries an empty `prompt_template` table from an
    # earlier session - the same orphan situation 77c12e0f0a01 documents for
    # `youtube_schedule`, but here the shape is exactly what this feature needs
    # (name VARCHAR, the three prompts TEXT), so it is adopted rather than
    # dropped. Guarded so the same revision still builds a fresh database.
    inspector = sa.inspect(op.get_bind())
    if "prompt_template" not in inspector.get_table_names():
        op.create_table(
            "prompt_template",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(), nullable=False, unique=True),
            sa.Column("system_prompt", sa.Text(), nullable=True),
            sa.Column("overlay_prompt", sa.Text(), nullable=True),
            sa.Column("image_prompt", sa.Text(), nullable=True),
        )
    if "prompt_template_id" not in [
        column["name"] for column in inspector.get_columns("draft")
    ]:
        op.add_column(
            "draft",
            sa.Column(
                "prompt_template_id",
                sa.Integer(),
                sa.ForeignKey("prompt_template.id"),
                nullable=True,
            ),
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "prompt_template_id" in [
        column["name"] for column in inspector.get_columns("draft")
    ]:
        op.drop_column("draft", "prompt_template_id")
    if "prompt_template" in inspector.get_table_names():
        op.drop_table("prompt_template")
