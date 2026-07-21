"""attendance_digest_config — davomat digesti vaqti botdan sozlanadi

Revision ID: c6d7e8f9a0b1
Revises: b5c6d7e8f9a0
Create Date: 2026-07-21 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c6d7e8f9a0b1"
down_revision: Union[str, None] = "b5c6d7e8f9a0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "attendance_digest_config",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("morning_hour", sa.Integer(), nullable=False, server_default="9"),
        sa.Column("morning_minute", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("evening_hour", sa.Integer(), nullable=False, server_default="22"),
        sa.Column("evening_minute", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("morning_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("evening_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("morning_last_posted", sa.Date(), nullable=True),
        sa.Column("evening_last_posted", sa.Date(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("attendance_digest_config")
