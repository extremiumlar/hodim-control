"""holidays — bayram kunlari (yangi TZ 2.9 / S-09)

Revision ID: v1w2x3y4z5a6
Revises: u0v1w2x3y4z5
Create Date: 2026-08-19

NEGA: tizim bayramni oddiy ish kuni deb sanardi — xodim kelmagani uchun
«kelmagan kun» ushlanmasiga tushardi va normalar bajarilmagan ko'rinardi.

`date` UNIKAL: HR ro'yxatni yildan yilga ko'chirganda takrorlash oson.
"""
from alembic import op
import sqlalchemy as sa

revision = "v1w2x3y4z5a6"
down_revision = "u0v1w2x3y4z5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "holidays",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("date", sa.Date(), nullable=False, unique=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("kind", sa.String(10), nullable=False, server_default="state"),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_holidays_date", "holidays", ["date"])


def downgrade() -> None:
    op.drop_index("ix_holidays_date", table_name="holidays")
    op.drop_table("holidays")
