"""Avans: payroll_adjustments ga tasdiq bosqichi va toifa

Revision ID: f5a6b7c8d9e0
Revises: e4f5a6b7c8d9
Create Date: 2026-08-13

NEGA (egasining talabi): avans tizimi web panelda umuman yo'q edi — model bor,
lekin oyna ham, ro'yxat endpointi ham yo'q. Endi HR avansni kiritadi, Boshliq
tasdiqlaydi, tasdiqlangach oy oxirida oylikdan avtomatik ayiriladi.

DIQQAT — `server_default` ATAYLAB: mavjud yozuvlar allaqachon hisobga kirgan.
Ular `status='approved'` bo'lib qolishi SHART, aks holda o'tgan oylarning
oylik hisobi jimgina o'zgarib ketardi.
"""
from alembic import op
import sqlalchemy as sa

revision = "f5a6b7c8d9e0"
down_revision = "e4f5a6b7c8d9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # batch_alter_table — SQLite ustun/FK qo'shishda jadvalni qayta quradi;
    # PostgreSQL'da (production) oddiy ALTER bo'lib ketadi.
    with op.batch_alter_table("payroll_adjustments") as batch:
        batch.add_column(
            sa.Column("category", sa.String(20), nullable=False, server_default="manual")
        )
        batch.add_column(
            sa.Column("status", sa.String(20), nullable=False, server_default="approved")
        )
        batch.add_column(sa.Column("issued_on", sa.Date(), nullable=True))
        batch.add_column(sa.Column("decided_by", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("decided_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("decided_note", sa.String(500), nullable=True))
    # `decided_by` uchun FK ATAYLAB qo'yilmadi: uni shu batch ichida qo'shish
    # alembic'ning SQLite batch rejimida `CircularDependencyError` beradi
    # (jadval qayta quriladi va yangi ustunlar tartibi chalkashadi). Modelda
    # `ForeignKey` qolgan — u niyatni hujjatlaydi va noldan quriladigan bazada
    # (create_all) haqiqiy cheklov bo'ladi. Bu maydon faqat AUDIT uchun
    # (kim tasdiqladi), unga tayanadigan JOIN yo'q.
    # Tasdiq kutayotgan avanslarni tez topish uchun (Boshliq sahifasi va
    # hisob-kitob ikkalasi ham shu bo'yicha filtrlaydi).
    op.create_index("ix_payroll_adjustments_status", "payroll_adjustments", ["status", "period"])


def downgrade() -> None:
    op.drop_index("ix_payroll_adjustments_status", table_name="payroll_adjustments")
    with op.batch_alter_table("payroll_adjustments") as batch:
        batch.drop_column("decided_note")
        batch.drop_column("decided_at")
        batch.drop_column("decided_by")
        batch.drop_column("issued_on")
        batch.drop_column("status")
        batch.drop_column("category")
