"""add work schedule tables

Revision ID: 0394ed6a9187
Revises: c72ca71126ba
Create Date: 2026-07-07 15:17:42.024938

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0394ed6a9187'
down_revision: Union[str, None] = 'c72ca71126ba'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "work_schedule_weekly",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("weekday", sa.Integer(), nullable=False),
        sa.Column("is_working", sa.Boolean(), nullable=False),
        sa.Column("start_time", sa.String(length=5), nullable=True),
        sa.Column("end_time", sa.String(length=5), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "weekday", name="uq_work_schedule_weekly"),
    )
    op.create_index(op.f("ix_work_schedule_weekly_user_id"), "work_schedule_weekly", ["user_id"])
    op.create_table(
        "work_schedule_override",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("is_working", sa.Boolean(), nullable=False),
        sa.Column("start_time", sa.String(length=5), nullable=True),
        sa.Column("end_time", sa.String(length=5), nullable=True),
        sa.Column("note", sa.String(length=255), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "date", name="uq_work_schedule_override"),
    )
    op.create_index(op.f("ix_work_schedule_override_user_id"), "work_schedule_override", ["user_id"])
    op.create_index(op.f("ix_work_schedule_override_date"), "work_schedule_override", ["date"])


def downgrade() -> None:
    op.drop_table("work_schedule_override")
    op.drop_table("work_schedule_weekly")
