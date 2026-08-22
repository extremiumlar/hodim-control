"""S-32: o'quv paneli — kurs, material va savol jadvallari (yangi TZ 3.1).

⚠️ IKKALA DIALEKTDA ishlashi kerak (SQLite lokal, PostgreSQL production).
Shuning uchun:
  • `sa.JSON()` — SQLAlchemy uni SQLite'da TEXT, Postgres'da JSON qiladi;
  • FK lar `create_table` ichida e'lon qilinadi (`batch_alter_table`
    kerak emas — jadval YANGI, mavjudini o'zgartirmayapmiz).

Revision ID: cr02f2a3b4c5
Revises: kb01e1f2a3b4
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "cr02f2a3b4c5"
down_revision = "kb01e1f2a3b4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "courses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("pass_percent", sa.Integer(), nullable=False, server_default="70"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "is_published", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_courses_is_published", "courses", ["is_published"])
    op.create_index("ix_courses_deleted_at", "courses", ["deleted_at"])

    op.create_table(
        "course_materials",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "course_id",
            sa.Integer(),
            sa.ForeignKey("courses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("kind", sa.String(12), nullable=False, server_default="text"),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        #  ⚠️ Video SERVERDA saqlanmaydi — Telegram `file_id` yoziladi.
        sa.Column("file_id", sa.String(512), nullable=True),
        sa.Column("url", sa.String(512), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_course_materials_course_id", "course_materials", ["course_id"])
    op.create_index("ix_course_materials_position", "course_materials", ["position"])
    op.create_index("ix_course_materials_deleted_at", "course_materials", ["deleted_at"])

    op.create_table(
        "course_questions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "course_id",
            sa.Integer(),
            sa.ForeignKey("courses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("options", sa.JSON(), nullable=True),
        sa.Column("correct_index", sa.Integer(), nullable=True),
        sa.Column("points", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_course_questions_course_id", "course_questions", ["course_id"])
    op.create_index("ix_course_questions_position", "course_questions", ["position"])
    op.create_index("ix_course_questions_deleted_at", "course_questions", ["deleted_at"])


def downgrade() -> None:
    op.drop_table("course_questions")
    op.drop_table("course_materials")
    op.drop_table("courses")
