"""explanation_requests — sababsiz kelmagan kun uchun tushuntirish xati

⚠️ Mavjud jarima mantiqiga TEGMAYDI — ustiga qo'shiladigan qatlam. HR
"sababli" deb qabul qilsa, MAVJUD ExcusedDay mexanizmi orqali kun sababliga
aylanadi va jarima o'z-o'zidan tushadi.

Revision ID: a8b9c0d1e2f4
Revises: f7a8b9c0d1e3
Create Date: 2026-08-03
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a8b9c0d1e2f4"
down_revision: Union[str, None] = "f7a8b9c0d1e3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "explanation_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("asked_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("answer_text", sa.Text(), nullable=True),
        sa.Column("answered_at", sa.DateTime(), nullable=True),
        sa.Column("decided_by", sa.Integer(), nullable=True),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["decided_by"], ["users.id"]),
        # Bir kunga bitta so'rov — kechqurungi job qayta ishlasa takrorlanmasin.
        sa.UniqueConstraint("user_id", "date", name="uq_explanation_user_date"),
    )
    op.create_index("ix_explanation_requests_user_id", "explanation_requests", ["user_id"])
    op.create_index("ix_explanation_requests_date", "explanation_requests", ["date"])
    op.create_index("ix_explanation_requests_status", "explanation_requests", ["status"])


def downgrade() -> None:
    op.drop_index("ix_explanation_requests_status", table_name="explanation_requests")
    op.drop_index("ix_explanation_requests_date", table_name="explanation_requests")
    op.drop_index("ix_explanation_requests_user_id", table_name="explanation_requests")
    op.drop_table("explanation_requests")
