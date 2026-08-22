"""S-37: kurs yig'ma raqamlari (yangi TZ 3.1).

⚠️ Bu jadval faqat KESH — cron qayta hisoblaydi. Ma'lumot yo'qolsa
hech narsa buzilmaydi, shuning uchun `downgrade` ham xavfsiz.

Revision ID: cr05c5d6e7f8
Revises: cr04b4c5d6e7
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "cr05c5d6e7f8"
down_revision = "cr04b4c5d6e7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "course_stats",
        sa.Column(
            "course_id",
            sa.Integer(),
            sa.ForeignKey("courses.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("material_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("question_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("assigned_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("not_started", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("in_progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("finished", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("passed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("pending_review", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("overdue", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("computed_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("course_stats")
