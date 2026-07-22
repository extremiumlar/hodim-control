"""operator_busy_periods — boshliq/dasturchi belgilaydigan band vaqt (real-vaqtli
harakatsizlik nazoratini vaqtincha to'xtatish uchun)

Revision ID: a1b2c3d4e5f6
Revises: f3a4b5c6d7e8
Create Date: 2026-07-22 17:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "f3a4b5c6d7e8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("ai_config") as batch_op:
        batch_op.add_column(
            sa.Column("idle_alerts_enabled", sa.Boolean(), nullable=False, server_default=sa.true())
        )

    op.create_table(
        "operator_busy_periods",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("set_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("start_at", sa.DateTime(), nullable=False),
        sa.Column("end_at", sa.DateTime(), nullable=False),
        sa.Column("reason", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    with op.batch_alter_table("operator_busy_periods") as batch_op:
        batch_op.create_index(op.f("ix_operator_busy_periods_user_id"), ["user_id"])
        batch_op.create_index(op.f("ix_operator_busy_periods_start_at"), ["start_at"])
        batch_op.create_index(op.f("ix_operator_busy_periods_end_at"), ["end_at"])


def downgrade() -> None:
    with op.batch_alter_table("operator_busy_periods") as batch_op:
        batch_op.drop_index(op.f("ix_operator_busy_periods_end_at"))
        batch_op.drop_index(op.f("ix_operator_busy_periods_start_at"))
        batch_op.drop_index(op.f("ix_operator_busy_periods_user_id"))
    op.drop_table("operator_busy_periods")

    with op.batch_alter_table("ai_config") as batch_op:
        batch_op.drop_column("idle_alerts_enabled")
