"""add operator AI tables (hourly_actual, operator_profile, hourly_target)

Revision ID: a1f2c3d4e5b6
Revises: 18357ae9244b
Create Date: 2026-07-08 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a1f2c3d4e5b6"
down_revision: Union[str, None] = "18357ae9244b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "hourly_actual",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("hour", sa.Integer(), nullable=False),
        sa.Column("calls", sa.Integer(), nullable=False),
        sa.Column("calls_in", sa.Integer(), nullable=False),
        sa.Column("calls_out", sa.Integer(), nullable=False),
        sa.Column("answered", sa.Integer(), nullable=False),
        sa.Column("talk_sec", sa.Integer(), nullable=False),
        sa.Column("short_calls", sa.Integer(), nullable=False),
        sa.Column("synced_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("user_id", "date", "hour", name="uq_hourly_actual_grain"),
    )
    op.create_index(op.f("ix_hourly_actual_user_id"), "hourly_actual", ["user_id"])
    op.create_index(op.f("ix_hourly_actual_date"), "hourly_actual", ["date"])

    op.create_table(
        "operator_profile",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("hour", sa.Integer(), nullable=False),
        sa.Column("baseline_calls", sa.Integer(), nullable=False),
        sa.Column("baseline_answered", sa.Integer(), nullable=False),
        sa.Column("baseline_talk_sec", sa.Integer(), nullable=False),
        sa.Column("sample_days", sa.Integer(), nullable=False),
        sa.Column("computed_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("user_id", "hour", name="uq_operator_profile_grain"),
    )
    op.create_index(op.f("ix_operator_profile_user_id"), "operator_profile", ["user_id"])

    op.create_table(
        "hourly_target",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("hour", sa.Integer(), nullable=False),
        sa.Column("target_calls", sa.Integer(), nullable=False),
        sa.Column("target_answered", sa.Integer(), nullable=False),
        sa.Column("target_talk_sec", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("user_id", "date", "hour", name="uq_hourly_target_grain"),
    )
    op.create_index(op.f("ix_hourly_target_user_id"), "hourly_target", ["user_id"])
    op.create_index(op.f("ix_hourly_target_date"), "hourly_target", ["date"])


def downgrade() -> None:
    op.drop_index(op.f("ix_hourly_target_date"), table_name="hourly_target")
    op.drop_index(op.f("ix_hourly_target_user_id"), table_name="hourly_target")
    op.drop_table("hourly_target")

    op.drop_index(op.f("ix_operator_profile_user_id"), table_name="operator_profile")
    op.drop_table("operator_profile")

    op.drop_index(op.f("ix_hourly_actual_date"), table_name="hourly_actual")
    op.drop_index(op.f("ix_hourly_actual_user_id"), table_name="hourly_actual")
    op.drop_table("hourly_actual")
