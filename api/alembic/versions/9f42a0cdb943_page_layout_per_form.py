"""page layout per form

One `page_layout` row per Page per card form, so a card and a full overlay can
carry different fonts and padding (client, 2026-10-22). The Page's pick of form
moves to `page.template`.

Each existing row's overrides are copied to every form, so nothing a Page draws
changes on upgrade. Downgrade keeps the `card` row and drops the rest.

Revision ID: 9f42a0cdb943
Revises: c61f29a47cd0
Create Date: 2026-10-22 15:30:58.459805

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
# SQLModel's own column types (AutoString) are rendered into these files by
# autogenerate, so the import has to be here even when a revision does not use it.
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '9f42a0cdb943'
down_revision: Union[str, Sequence[str], None] = 'c61f29a47cd0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

FORMS = ("card", "full_overlay", "photo", "quote")


def upgrade() -> None:
    op.add_column('page', sa.Column('template', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    op.execute(
        "UPDATE page SET template = pl.template FROM page_layout pl WHERE pl.page_id = page.id"
    )

    op.add_column('page_layout', sa.Column('form', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    op.execute("UPDATE page_layout SET form = 'card'")
    op.alter_column('page_layout', 'form', nullable=False)
    op.drop_column('page_layout', 'template')

    op.drop_index(op.f('ix_page_layout_page_id'), table_name='page_layout')
    op.create_index(op.f('ix_page_layout_page_id'), 'page_layout', ['page_id'], unique=False)
    op.create_unique_constraint('uq_page_layout_page_form', 'page_layout', ['page_id', 'form'])

    columns = [
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns('page_layout')
        if column["name"] not in ("id", "form")
    ]
    listed = ", ".join(columns)
    for form in FORMS[1:]:
        op.execute(
            f"INSERT INTO page_layout ({listed}, form) "
            f"SELECT {listed}, '{form}' FROM page_layout WHERE form = 'card'"
        )


def downgrade() -> None:
    op.execute("DELETE FROM page_layout WHERE form <> 'card'")
    op.add_column('page_layout', sa.Column('template', sa.VARCHAR(), autoincrement=False, nullable=True))
    op.execute(
        "UPDATE page_layout SET template = p.template FROM page p WHERE p.id = page_layout.page_id"
    )
    op.drop_constraint('uq_page_layout_page_form', 'page_layout', type_='unique')
    op.drop_index(op.f('ix_page_layout_page_id'), table_name='page_layout')
    op.create_index(op.f('ix_page_layout_page_id'), 'page_layout', ['page_id'], unique=True)
    op.drop_column('page_layout', 'form')
    op.drop_column('page', 'template')
