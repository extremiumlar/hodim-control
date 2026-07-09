"""add shortfall_reason (Operator AI sabab halqasi)

Revision ID: c3d4e5f6a7b8
Revises: b7c8d9e0f1a2
Create Date: 2026-07-09 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, None] = "b7c8d9e0f1a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "shortfall_reason",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("hour", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("user_id", "date", "hour", name="uq_shortfall_reason_grain"),
    )
    op.create_index(op.f("ix_shortfall_reason_user_id"), "shortfall_reason", ["user_id"])
    op.create_index(op.f("ix_shortfall_reason_date"), "shortfall_reason", ["date"])


def downgrade() -> None:
    op.drop_index(op.f("ix_shortfall_reason_date"), table_name="shortfall_reason")
    op.drop_index(op.f("ix_shortfall_reason_user_id"), table_name="shortfall_reason")
    op.drop_table("shortfall_reason")
