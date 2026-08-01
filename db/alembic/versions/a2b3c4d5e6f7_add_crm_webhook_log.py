"""Uysot CRM webhook xom-so'rov jurnali (crm_webhook_log).

Uysot 2026-08-01 da webhook'ni ochdi (hozircha faqat lid eventlari), payload
formati hujjatlashtirilmagan — bu jadval formatni jonli oqimdan o'rganish va
diagnostika uchun (db/models.py:CrmWebhookLog izohiga qarang).

Revision ID: a2b3c4d5e6f7
Revises: 8b7c6d5e4f3a
Create Date: 2026-08-01
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a2b3c4d5e6f7"
down_revision: Union[str, None] = "8b7c6d5e4f3a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "crm_webhook_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("received_at", sa.DateTime(), nullable=False),
        sa.Column("remote_ip", sa.String(length=64), nullable=True),
        sa.Column("headers", sa.JSON(), nullable=True),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("parsed_events", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("note", sa.String(length=255), nullable=True),
    )
    op.create_index("ix_crm_webhook_log_received_at", "crm_webhook_log", ["received_at"])


def downgrade() -> None:
    op.drop_index("ix_crm_webhook_log_received_at", table_name="crm_webhook_log")
    op.drop_table("crm_webhook_log")
