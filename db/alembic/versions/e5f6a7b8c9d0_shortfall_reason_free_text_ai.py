"""shortfall_reason: erkin matn + AI tasnif + tekshiruv ustunlari

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-07-09 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # batch_alter_table — SQLite ALTER cheklovlari uchun (reason NULL'ga o'tkaziladi)
    with op.batch_alter_table("shortfall_reason") as batch:
        batch.alter_column("reason", existing_type=sa.String(length=64), nullable=True)
        batch.add_column(sa.Column("raw_text", sa.Text(), nullable=True))
        batch.add_column(sa.Column("ai_category", sa.String(length=32), nullable=True))
        batch.add_column(sa.Column("verified", sa.Boolean(), nullable=True))
        batch.add_column(sa.Column("verify_note", sa.String(length=255), nullable=True))
        batch.add_column(sa.Column("answered_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    # Javobsiz (pending, reason IS NULL) yozuvlar eski NOT NULL sxemaga sig'maydi
    op.execute("DELETE FROM shortfall_reason WHERE reason IS NULL")
    with op.batch_alter_table("shortfall_reason") as batch:
        batch.drop_column("answered_at")
        batch.drop_column("verify_note")
        batch.drop_column("verified")
        batch.drop_column("ai_category")
        batch.drop_column("raw_text")
        batch.alter_column("reason", existing_type=sa.String(length=64), nullable=False)
