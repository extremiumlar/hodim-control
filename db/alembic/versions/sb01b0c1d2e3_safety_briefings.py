"""S-48: texnika xavfsizligi instruktaji jurnali (yangi TZ 3.6).

⚠️ QATNASHCHILAR JADVALI YARATILMAYDI. Imzolar S-20 ning umumiy
`acknowledgements` jadvalida (`object_type="briefing"`) — TZ ham
shuni ko'rsatadi. Alohida jadval qilinsa tanishuv eslatmasi (S-42)
bu turga ishlamasdi.

⚠️ FK lar MODELDA, bu yerda oddiy `Integer` (loyiha naqshi):
SQLite `batch_alter_table` nomsiz FK bilan yiqiladi.

Revision ID: sb01b0c1d2e3
Revises: ob02a9b0c1d2
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "sb01b0c1d2e3"
down_revision = "ob02a9b0c1d2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "safety_briefings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("held_on", sa.Date(), nullable=False),
        sa.Column("conducted_by", sa.Integer(), nullable=True),
        sa.Column("course_id", sa.Integer(), nullable=True),
        sa.Column("repeat_months", sa.Integer(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_sb_kind", "safety_briefings", ["kind"])
    op.create_index("ix_sb_held_on", "safety_briefings", ["held_on"])
    op.create_index("ix_sb_course", "safety_briefings", ["course_id"])
    op.create_index("ix_sb_deleted", "safety_briefings", ["deleted_at"])


def downgrade() -> None:
    op.drop_table("safety_briefings")
