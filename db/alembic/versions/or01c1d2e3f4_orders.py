"""S-50: buyruqlar reyestri (yangi TZ 3.21).

⚠️ `number` da UNIQUE cheklov — buyruq raqami huquqiy rekvizit va
ikkita buyruq bir xil raqam bilan chiqsa qaysi biri haqiqiy ekani
noma'lum bo'ladi. Kod darajasidagi «max + 1» yetarli EMAS: parallel
so'rovda ikkovi bir xil sonni ko'radi, shuning uchun BAZA cheklovi
+ qayta urinish.

Revision ID: or01c1d2e3f4
Revises: sb01b0c1d2e3
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "or01c1d2e3f4"
down_revision = "sb01b0c1d2e3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "orders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("number", sa.String(length=20), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("order_date", sa.Date(), nullable=False),
        sa.Column("params", sa.JSON(), nullable=True),
        sa.Column("file_id", sa.String(length=512), nullable=True),
        sa.Column("status", sa.String(length=12), nullable=False, server_default="active"),
        sa.Column("cancels_order_id", sa.Integer(), nullable=True),
        sa.Column("cancel_reason", sa.Text(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("number", name="uq_orders_number"),
    )
    op.create_index("ix_orders_number", "orders", ["number"])
    op.create_index("ix_orders_kind", "orders", ["kind"])
    op.create_index("ix_orders_user", "orders", ["user_id"])
    op.create_index("ix_orders_date", "orders", ["order_date"])
    op.create_index("ix_orders_status", "orders", ["status"])
    op.create_index("ix_orders_cancels", "orders", ["cancels_order_id"])


def downgrade() -> None:
    op.drop_table("orders")
