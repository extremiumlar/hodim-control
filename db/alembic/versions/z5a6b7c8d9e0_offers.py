"""offers — ish takliflari (yangi TZ 3.3 / S-15)

Revision ID: z5a6b7c8d9e0
Revises: y4z5a6b7c8d9
Create Date: 2026-08-20

`salary` — INTEGER (TZ qabul mezoni): matn bo'lsa «12 mln»,
«12,000,000», «12000000 so'm» aralashib, taqqoslash ishlamasdi.
"""
from alembic import op
import sqlalchemy as sa

revision = "z5a6b7c8d9e0"
down_revision = "y4z5a6b7c8d9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "offers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("candidate_name", sa.String(200), nullable=False),
        sa.Column("phone", sa.String(32), nullable=True),
        sa.Column("position_id", sa.Integer(), sa.ForeignKey("positions.id"), nullable=True),
        sa.Column("position_text", sa.String(200), nullable=True),
        sa.Column("salary", sa.Integer(), nullable=False),
        sa.Column("probation_months", sa.Integer(), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("manager_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("status", sa.String(12), nullable=False, server_default="draft"),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("note", sa.String(500), nullable=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_offers_candidate_name", "offers", ["candidate_name"])
    op.create_index("ix_offers_status", "offers", ["status"])


def downgrade() -> None:
    op.drop_index("ix_offers_status", table_name="offers")
    op.drop_index("ix_offers_candidate_name", table_name="offers")
    op.drop_table("offers")
