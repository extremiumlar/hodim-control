"""Bot FSM holati uchun jadval (cPanel webhook rejimi)

Passenger ishchi jarayonlarni qayta ochganda MemoryStorage yo'qolib, ko'p
bosqichli bot oqimlari (javob tahriri, ma'lumot qo'shish, vaqt kiritish...)
uzilib qolardi — endi holat bazada saqlanadi.

Revision ID: a4b5c6d7e8f9
Revises: f2a3b4c5d6e7
Create Date: 2026-07-18
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a4b5c6d7e8f9"
down_revision: Union[str, None] = "f2a3b4c5d6e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "fsm_states",
        sa.Column("key", sa.String(length=64), primary_key=True),
        sa.Column("state", sa.String(length=128), nullable=True),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("fsm_states")
