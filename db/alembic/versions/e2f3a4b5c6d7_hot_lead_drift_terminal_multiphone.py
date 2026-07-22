"""hot_lead: mas'ul drift, terminal yopilish, ko'p-telefon, navbat-xavfsiz eskalatsiya

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
Create Date: 2026-07-22 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e2f3a4b5c6d7"
down_revision: Union[str, None] = "d1e2f3a4b5c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("hot_lead") as batch_op:
        batch_op.add_column(sa.Column("phones", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("last_call_check_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("correction_sent_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("reassigned_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("resolved_reason", sa.String(255), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("hot_lead") as batch_op:
        batch_op.drop_column("resolved_reason")
        batch_op.drop_column("reassigned_at")
        batch_op.drop_column("correction_sent_at")
        batch_op.drop_column("last_call_check_at")
        batch_op.drop_column("phones")
