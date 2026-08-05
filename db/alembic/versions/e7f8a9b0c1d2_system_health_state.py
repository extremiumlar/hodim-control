"""crm_health_state -> system_health_state (har tekshiruv uchun alohida qator).

Qo'riqchi endi faqat CRM emas, zaxira nusxa va davomat oqimini ham kuzatadi
(db/models.py: SystemHealthState). Eski jadval bir necha soat oldin qo'shilgan
va faqat qo'riqchining ichki holatini saqlagan — biznes ma'lumoti yo'q,
shuning uchun ko'chirilmasdan qayta yaratiladi.

Revision ID: e7f8a9b0c1d2
Revises: d6e7f8a9b0c1
Create Date: 2026-08-05
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e7f8a9b0c1d2"
down_revision: Union[str, None] = "d6e7f8a9b0c1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "system_health_state",
        sa.Column("check", sa.String(length=32), primary_key=True),
        sa.Column("alerting", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("last_alert_at", sa.DateTime(), nullable=True),
        sa.Column("stale_since", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.drop_table("crm_health_state")


def downgrade() -> None:
    op.create_table(
        "crm_health_state",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("alerting", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("last_alert_at", sa.DateTime(), nullable=True),
        sa.Column("stale_since", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.drop_table("system_health_state")
