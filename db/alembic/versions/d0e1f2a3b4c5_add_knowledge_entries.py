"""Sotuv bilim bazasi jadvali (knowledge_entries)

Anketa javoblaridan (ingest → AI ishlovi → rahbar tasdig'i) va qo'lda kiritilgan
rasmiy faktlardan yig'iladigan savol-javob bazasi. Sotuv AI (keyingi bosqich)
faqat verified yozuvlardan foydalanadi.

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-07-17
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d0e1f2a3b4c5"
down_revision: Union[str, None] = "c9d0e1f2a3b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "knowledge_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.String(length=10), nullable=False, server_default="single"),
        sa.Column("group_key", sa.String(length=30), nullable=True),
        sa.Column("category", sa.String(length=30), nullable=False, server_default="umumiy"),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="draft"),
        sa.Column("date_sensitive", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("needs_recheck", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("recheck_notified_at", sa.DateTime(), nullable=True),
        sa.Column("source", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("source_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column(
            "session_id",
            sa.Integer(),
            sa.ForeignKey("anketa_sessions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "anketa_answer_id",
            sa.Integer(),
            sa.ForeignKey("anketa_answers.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("ai_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("verified_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("verified_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_knowledge_entries_status", "knowledge_entries", ["status"])
    op.create_index("ix_knowledge_entries_group_key", "knowledge_entries", ["group_key"])
    op.create_index("ix_knowledge_entries_session_id", "knowledge_entries", ["session_id"])


def downgrade() -> None:
    op.drop_index("ix_knowledge_entries_session_id", table_name="knowledge_entries")
    op.drop_index("ix_knowledge_entries_group_key", table_name="knowledge_entries")
    op.drop_index("ix_knowledge_entries_status", table_name="knowledge_entries")
    op.drop_table("knowledge_entries")
