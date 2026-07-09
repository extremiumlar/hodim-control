"""add hot_lead (issiq lid speed-to-lead, 5-bosqich) + ai_config.hot_leads_enabled

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-07-09 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "hot_lead",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("crm_lead_id", sa.Integer(), nullable=False),
        sa.Column("lead_name", sa.String(length=64), nullable=True),
        sa.Column("contact_name", sa.String(length=255), nullable=True),
        sa.Column("phone", sa.String(length=32), nullable=True),
        sa.Column("source", sa.String(length=64), nullable=True),
        sa.Column("responsible_crm_id", sa.Integer(), nullable=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_ts", sa.Integer(), nullable=False),
        sa.Column("detected_at", sa.DateTime(), nullable=False),
        sa.Column("notified_at", sa.DateTime(), nullable=True),
        sa.Column("claimed_at", sa.DateTime(), nullable=True),
        sa.Column("first_call_at", sa.DateTime(), nullable=True),
        sa.Column("first_call_sec", sa.Integer(), nullable=True),
        sa.Column("escalated_at", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
    )
    op.create_index("ix_hot_lead_crm_lead_id", "hot_lead", ["crm_lead_id"], unique=True)
    op.create_index("ix_hot_lead_user_id", "hot_lead", ["user_id"])
    op.create_index("ix_hot_lead_status", "hot_lead", ["status"])

    with op.batch_alter_table("ai_config") as batch:
        batch.add_column(
            sa.Column("hot_leads_enabled", sa.Boolean(), nullable=False, server_default=sa.true())
        )


def downgrade() -> None:
    with op.batch_alter_table("ai_config") as batch:
        batch.drop_column("hot_leads_enabled")
    op.drop_index("ix_hot_lead_status", table_name="hot_lead")
    op.drop_index("ix_hot_lead_user_id", table_name="hot_lead")
    op.drop_index("ix_hot_lead_crm_lead_id", table_name="hot_lead")
    op.drop_table("hot_lead")
