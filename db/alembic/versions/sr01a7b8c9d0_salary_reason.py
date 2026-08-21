"""salary_rates.reason — ish haqi nega o'zgardi (yangi TZ 3.25 / S-25)

Revision ID: sr01a7b8c9d0
Revises: st01f6a7b8c9
Create Date: 2026-08-20

⚠️ ESKI QATORLAR `NULL` QOLADI va bu ATAYLAB (TZ qabul mezoni:
«eski qatorlarda `reason` NULL — kiritilmagan deb ko'rsatiladi»).

Migratsiya ularni taxmin bilan to'ldirmaydi: noto'g'ri sabab yo'q
sababdan YOMONROQ, chunki u tahlilni buzadi — «natija bo'yicha nechta
oshirdik?» degan savolga soxta raqam beradi.
"""
from alembic import op
import sqlalchemy as sa

revision = "sr01a7b8c9d0"
down_revision = "st01f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("salary_rates") as batch:
        batch.add_column(sa.Column("reason", sa.String(16), nullable=True))
    op.create_index("ix_salary_rates_reason", "salary_rates", ["reason"])


def downgrade() -> None:
    op.drop_index("ix_salary_rates_reason", table_name="salary_rates")
    with op.batch_alter_table("salary_rates") as batch:
        batch.drop_column("reason")
