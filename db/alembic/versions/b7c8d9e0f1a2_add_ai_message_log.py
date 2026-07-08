"""add ai_message_log (Operator AI Claude qatlami audit/xotira)

Revision ID: b7c8d9e0f1a2
Revises: a1f2c3d4e5b6
Create Date: 2026-07-08 01:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b7c8d9e0f1a2"
down_revision: Union[str, None] = "a1f2c3d4e5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ai_message_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("context", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(op.f("ix_ai_message_log_user_id"), "ai_message_log", ["user_id"])
    op.create_index(op.f("ix_ai_message_log_kind"), "ai_message_log", ["kind"])
    op.create_index(op.f("ix_ai_message_log_created_at"), "ai_message_log", ["created_at"])


def downgrade() -> None:
    op.drop_index(op.f("ix_ai_message_log_created_at"), table_name="ai_message_log")
    op.drop_index(op.f("ix_ai_message_log_kind"), table_name="ai_message_log")
    op.drop_index(op.f("ix_ai_message_log_user_id"), table_name="ai_message_log")
    op.drop_table("ai_message_log")
