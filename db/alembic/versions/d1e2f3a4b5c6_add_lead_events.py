"""add crm_lead_state + lead_events — diff-asosidagi lid voqealari jurnali

Revision ID: d1e2f3a4b5c6
Revises: c6d7e8f9a0b1
Create Date: 2026-07-21 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d1e2f3a4b5c6"
down_revision: Union[str, None] = "c6d7e8f9a0b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "crm_lead_state",
        sa.Column("crm_lead_id", sa.Integer(), primary_key=True),
        sa.Column("pipe_status_id", sa.Integer(), nullable=False),
        sa.Column("stage_name", sa.String(255), nullable=False),
        sa.Column("responsible_id", sa.Integer(), nullable=True),
        sa.Column("responsible_name", sa.String(255), nullable=True),
        sa.Column("first_responsible_id", sa.Integer(), nullable=True),
        sa.Column("crm_updated_ts", sa.Integer(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "lead_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("crm_lead_id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(20), nullable=False),
        sa.Column("from_pipe_status_id", sa.Integer(), nullable=True),
        sa.Column("from_stage_name", sa.String(255), nullable=True),
        sa.Column("to_pipe_status_id", sa.Integer(), nullable=False),
        sa.Column("to_stage_name", sa.String(255), nullable=False),
        sa.Column("from_responsible_id", sa.Integer(), nullable=True),
        sa.Column("to_responsible_id", sa.Integer(), nullable=True),
        sa.Column("to_responsible_name", sa.String(255), nullable=True),
        sa.Column("first_responsible_id", sa.Integer(), nullable=True),
        sa.Column("crm_updated_ts", sa.Integer(), nullable=False),
        sa.Column("detected_at", sa.DateTime(), nullable=False),
    )
    with op.batch_alter_table("lead_events") as batch_op:
        batch_op.create_index(op.f("ix_lead_events_crm_lead_id"), ["crm_lead_id"])
        batch_op.create_index(op.f("ix_lead_events_event_type"), ["event_type"])
        batch_op.create_index(op.f("ix_lead_events_detected_at"), ["detected_at"])


def downgrade() -> None:
    with op.batch_alter_table("lead_events") as batch_op:
        batch_op.drop_index(op.f("ix_lead_events_detected_at"))
        batch_op.drop_index(op.f("ix_lead_events_event_type"))
        batch_op.drop_index(op.f("ix_lead_events_crm_lead_id"))
    op.drop_table("lead_events")
    op.drop_table("crm_lead_state")
