"""CRM aloqasi qo'riqchisining holati (crm_health_state).

2026-08-04 da Uysot tokeni bekor qilinib, tizim 27 soat jimgina ko'r bo'lib
qoldi. Qo'riqchi shuni aniqlab guruhga ogohlantiradi; holat bazada saqlanadi,
chunki production cron rejimida har daqiqa yangi jarayon ko'tariladi
(db/models.py: CrmHealthState izohiga qarang).

Revision ID: d6e7f8a9b0c1
Revises: c5d6e7f8a9b0
Create Date: 2026-08-05
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d6e7f8a9b0c1"
down_revision: Union[str, None] = "c5d6e7f8a9b0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "crm_health_state",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("alerting", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("last_alert_at", sa.DateTime(), nullable=True),
        sa.Column("stale_since", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("crm_health_state")
