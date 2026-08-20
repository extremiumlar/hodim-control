"""avans manbasi — payroll_adjustments.source (Avans TZ, A-01)

Revision ID: av01a1b2c3d4
Revises: a6b7c8d9e0f1
Create Date: 2026-08-20

Avansning ikkita kirish yo'li bor va ikkalasi ham BITTA jadvalga yozadi
(`PayrollAdjustment(category='advance')`): xodim arizasi (`requests.py`) va
HR ning «Ish haqi → Avans» sahifasi (`payroll.py`). Jadval bitta bo'lgani
to'g'ri — payslip uni bir marta yig'adi. Lekin manba ko'rinmagani uchun
HR ariza orqali allaqachon yozilgan avansni qo'lda ham kiritishi mumkin
edi — pul ikki marta ayirilardi.

Eski qatorlar: `source_request_id` bor bo'lsa «request», aks holda
«hr_manual» (avansdan boshqa toifadagi qatorlar tegilmaydi — ular uchun
manba tushunchasi yo'q, NULL qoladi).
"""
from alembic import op
import sqlalchemy as sa

revision = "av01a1b2c3d4"
down_revision = "a6b7c8d9e0f1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("payroll_adjustments") as batch:
        batch.add_column(sa.Column("source", sa.String(16), nullable=True))
    op.create_index(
        "ix_payroll_adjustments_source", "payroll_adjustments", ["source"]
    )
    # Faqat avanslarni to'ldiramiz.
    op.execute(
        "UPDATE payroll_adjustments SET source = 'request' "
        "WHERE category = 'advance' AND source_request_id IS NOT NULL"
    )
    op.execute(
        "UPDATE payroll_adjustments SET source = 'hr_manual' "
        "WHERE category = 'advance' AND source_request_id IS NULL"
    )


def downgrade() -> None:
    op.drop_index("ix_payroll_adjustments_source", table_name="payroll_adjustments")
    with op.batch_alter_table("payroll_adjustments") as batch:
        batch.drop_column("source")
