"""add lead_stage_daily snapshot table

Revision ID: 31420192559e
Revises: c7e2f8a91d34
Create Date: 2026-07-06 15:56:13.351234

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '31420192559e'
down_revision: Union[str, None] = 'c7e2f8a91d34'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "lead_stage_daily",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("pipe_status_id", sa.Integer(), nullable=False),
        sa.Column("stage_name", sa.String(length=255), nullable=False),
        sa.Column("leads_count", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("date", "pipe_status_id", name="uq_lead_stage_daily_date_status"),
    )
    op.create_index(op.f("ix_lead_stage_daily_date"), "lead_stage_daily", ["date"])


def downgrade() -> None:
    op.drop_index(op.f("ix_lead_stage_daily_date"), table_name="lead_stage_daily")
    op.drop_table("lead_stage_daily")
