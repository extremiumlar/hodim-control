"""avans «to'lab berildi» holati — issued_by/issued_at (Avans TZ, A-04)

Revision ID: av02b2c3d4e5
Revises: av01a1b2c3d4
Create Date: 2026-08-20

Ilgari «berilgan sana» KIRITISHDA so'ralardi, tasdiq esa keyin kelardi —
ya'ni pul Boshliq rad etishi mumkin bo'lgan paytda allaqachon qo'lda
bo'lardi va qaytarib olinmasdi. Endi holat zanjiri:

    pending → approved (ruxsat) → issued (kassa pulni berdi)
            ↘ rejected

MAVJUD QATORLAR: `approved` bo'lib `issued_on` to'ldirilganlar aslida
allaqachon TO'LANGAN — ular `issued` ga o'tkaziladi, aks holda HR
ro'yxatida «to'lanmagan» bo'lib ko'rinib, ikkinchi marta to'lanishi
mumkin edi. `issued_by`/`issued_at` ular uchun qaror ma'lumotidan
olinadi (kim tasdiqlagan bo'lsa, o'sha paytda berilgan deb yozamiz —
haqiqiy kassa izi yo'q, taxmin qilib boshqa odamni yozgandan ko'ra
qarorni manba qilgan aniqroq).

⚠️ PUL O'ZGARMAYDI: `build_payslip` shu bosqichda `approved` bilan bir
qatorda `issued` ni ham hisobga oladi, ya'ni o'tgan oylar summasi
o'sha-o'sha qoladi.
"""
from alembic import op
import sqlalchemy as sa

revision = "av02b2c3d4e5"
down_revision = "av01a1b2c3d4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("payroll_adjustments") as batch:
        batch.add_column(sa.Column("issued_by", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("issued_at", sa.DateTime(), nullable=True))
    op.execute(
        "UPDATE payroll_adjustments "
        "SET status = 'issued', "
        "    issued_by = decided_by, "
        "    issued_at = COALESCE(decided_at, created_at) "
        "WHERE category = 'advance' AND status = 'approved' AND issued_on IS NOT NULL"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE payroll_adjustments SET status = 'approved' "
        "WHERE category = 'advance' AND status = 'issued'"
    )
    with op.batch_alter_table("payroll_adjustments") as batch:
        batch.drop_column("issued_at")
        batch.drop_column("issued_by")
