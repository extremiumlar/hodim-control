"""Telegram ID ustunlarini BigInteger'ga o'tkazish.

Telegram foydalanuvchi ID'lari 2^31 dan oshadi (jonli misol: 6903942240),
guruh chat ID'lari esa manfiy va katta (-1003956495713). SQLite'da hamma
INTEGER 64-bit bo'lgani uchun bu xato YASHIRIN edi; PostgreSQL'da esa
INTEGER=int32 — "value out of int32 range" (PG'ga ko'chirish sinovi ushladi).

batch_alter_table — SQLite ALTER COLUMN TYPE'ni qo'llamaydi, batch rejimi
jadvalni qayta qurib beradi; PostgreSQL'da esa oddiy ALTER bo'lib tushadi.

Revision ID: 9c8d7e6f5a4b
Revises: f7a8b9c0d1e2
Create Date: 2026-07-31
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "9c8d7e6f5a4b"
down_revision: Union[str, None] = "f7a8b9c0d1e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COLUMNS = [
    ("teams", "telegram_group_id"),
    ("users", "telegram_id"),
    ("app_login_tokens", "telegram_id"),
    ("mobilograf_videos", "group_chat_id"),
]


def upgrade() -> None:
    for table, column in _COLUMNS:
        with op.batch_alter_table(table) as batch:
            batch.alter_column(
                column, type_=sa.BigInteger(), existing_type=sa.Integer(), existing_nullable=True
            )


def downgrade() -> None:
    for table, column in _COLUMNS:
        with op.batch_alter_table(table) as batch:
            batch.alter_column(
                column, type_=sa.Integer(), existing_type=sa.BigInteger(), existing_nullable=True
            )
