"""S-42: yo'riqnoma tanishuvi eslatmalari (yangi TZ 3.16).

`acknowledgements` ga eslatma hisobi qo'shiladi. Sanoq (obyekt,
versiya) bo'yicha, ya'ni yangi versiya uchun noldan boshlanadi.

⚠️ Mavjud qatorlarga `0` beriladi (`server_default`), aks holda
NOT NULL ustun bo'sh qiymat bilan qolib, birinchi eslatma tickida
`None + 1` xatosi chiqardi.

Revision ID: ak01e7f8a9b0
Revises: og01d6e7f8a9
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "ak01e7f8a9b0"
down_revision = "og01d6e7f8a9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("acknowledgements") as b:
        b.add_column(
            sa.Column(
                "reminder_count",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )
        b.add_column(sa.Column("last_reminded_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("acknowledgements") as b:
        b.drop_column("last_reminded_at")
        b.drop_column("reminder_count")
