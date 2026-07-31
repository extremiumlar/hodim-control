"""hot_lead.phone uzunligini 32 -> 128 ga kengaytirish.

Jonli CRM ma'lumotida bir nechta raqam qo'shilib kelgan holatlar bor (65+
belgi). SQLite VARCHAR uzunligini tekshirmaydi — xato yashirin edi;
PostgreSQL qat'iy ("value too long for type character varying(32)",
PG'ga ko'chirish sinovi ushladi).

Revision ID: 8b7c6d5e4f3a
Revises: 9c8d7e6f5a4b
Create Date: 2026-07-31
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "8b7c6d5e4f3a"
down_revision: Union[str, None] = "9c8d7e6f5a4b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("hot_lead") as batch:
        batch.alter_column(
            "phone", type_=sa.String(128), existing_type=sa.String(32), existing_nullable=True
        )


def downgrade() -> None:
    with op.batch_alter_table("hot_lead") as batch:
        batch.alter_column(
            "phone", type_=sa.String(32), existing_type=sa.String(128), existing_nullable=True
        )
