"""S-28: xodim murojaatlari jurnali (yangi TZ 3.29).

Revision ID: hi01d0e1f2a3
Revises: cr01c9d0e1f2
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "hi01d0e1f2a3"
down_revision = "cr01c9d0e1f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "hr_inquiries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=True),
        sa.Column("category", sa.String(16), nullable=False, server_default="other"),
        sa.Column(
            "category_auto", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("status", sa.String(12), nullable=False, server_default="open"),
        sa.Column("answered_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("answered_at", sa.DateTime(), nullable=True),
        sa.Column("knowledge_entry_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_hr_inquiries_user_id", "hr_inquiries", ["user_id"])
    op.create_index("ix_hr_inquiries_category", "hr_inquiries", ["category"])
    op.create_index("ix_hr_inquiries_created_at", "hr_inquiries", ["created_at"])
    #  HR paneli «javobsizlar»ni birinchi ko'rsatadi — eng ko'p
    #  ishlatiladigan filtr shu, alohida indeks bilan.
    op.create_index("ix_hr_inquiries_status", "hr_inquiries", ["status"])


def downgrade() -> None:
    op.drop_index("ix_hr_inquiries_status", table_name="hr_inquiries")
    op.drop_index("ix_hr_inquiries_created_at", table_name="hr_inquiries")
    op.drop_index("ix_hr_inquiries_category", table_name="hr_inquiries")
    op.drop_index("ix_hr_inquiries_user_id", table_name="hr_inquiries")
    op.drop_table("hr_inquiries")
