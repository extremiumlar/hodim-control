"""add ai_config (Operator AI rahbar boshqaruvi, 6-bosqich)

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-07-09 01:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ai_config",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("nudges_enabled", sa.Boolean(), nullable=False),
        sa.Column("group_summary_enabled", sa.Boolean(), nullable=False),
        sa.Column("weekly_enabled", sa.Boolean(), nullable=False),
        sa.Column("summary_hour", sa.Integer(), nullable=False),
        sa.Column("summary_minute", sa.Integer(), nullable=False),
        sa.Column("summary_last_posted", sa.Date(), nullable=True),
        sa.Column("weekly_last_posted", sa.Date(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("ai_config")
