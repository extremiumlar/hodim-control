"""Bilim bazasi anketasi jadvallari (sessiya + biriktirma + javoblar)

Dasturchi bot orqali kun/vaqtni tasdiqlaydi (anketa_sessions), har xodimga
bitta takrorlanmas savol to'plami biriktiriladi (anketa_assignments, savollar
api/services/anketa_data.py'da), javoblar matn ko'rinishida saqlanadi
(anketa_answers).

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-07-16
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c9d0e1f2a3b4"
down_revision: Union[str, None] = "b8c9d0e1f2a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "anketa_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="scheduled"),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_anketa_sessions_status", "anketa_sessions", ["status"])

    op.create_table(
        "anketa_assignments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "session_id",
            sa.Integer(),
            sa.ForeignKey("anketa_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("toplam", sa.Integer(), nullable=False),
        sa.Column("current_q", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("session_id", "user_id", name="uq_anketa_assignment_user"),
        sa.UniqueConstraint("session_id", "toplam", name="uq_anketa_assignment_toplam"),
    )
    op.create_index("ix_anketa_assignments_session_id", "anketa_assignments", ["session_id"])
    op.create_index("ix_anketa_assignments_user_id", "anketa_assignments", ["user_id"])

    op.create_table(
        "anketa_answers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "assignment_id",
            sa.Integer(),
            sa.ForeignKey("anketa_assignments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("question_index", sa.Integer(), nullable=False),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("answer_text", sa.Text(), nullable=False),
        sa.Column("answered_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("assignment_id", "question_index", name="uq_anketa_answer_q"),
    )
    op.create_index("ix_anketa_answers_assignment_id", "anketa_answers", ["assignment_id"])


def downgrade() -> None:
    op.drop_index("ix_anketa_answers_assignment_id", table_name="anketa_answers")
    op.drop_table("anketa_answers")
    op.drop_index("ix_anketa_assignments_user_id", table_name="anketa_assignments")
    op.drop_index("ix_anketa_assignments_session_id", table_name="anketa_assignments")
    op.drop_table("anketa_assignments")
    op.drop_index("ix_anketa_sessions_status", table_name="anketa_sessions")
    op.drop_table("anketa_sessions")
