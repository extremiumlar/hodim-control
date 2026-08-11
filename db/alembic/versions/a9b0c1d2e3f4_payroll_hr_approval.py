"""payroll_periods: HR tasdiq bosqichi (vazifalar ajratildi)

Ilgari oylikni HR o'zi hisoblab, o'zi tasdiqlab, davrni QULFLAB qo'yardi —
bitta odam butun pul jarayonini boshidan oxirigacha yakunlardi. Sinovda
tasdiqlangan: HR tokeni bilan `calculate` va `approve` ketma-ket 200
qaytardi, hech kim aralashmadi. Egasining talabi: "hr uni belgilaydi,
boss boshliq uni tasdiqlaydi".

Endi ikki bosqich:
  calculated -> hr_approved (HR: "tekshirdim, tayyor", qulflamaydi)
             -> approved    (Boshliq/Dasturchi: yakuniy, locked=True)

`status` — String ustun, ya'ni yangi qiymat uchun sxema o'zgarishi shart
emas. Faqat ikkita yangi ustun qo'shiladi: kim va qachon HR bosqichidan
o'tkazgani. Ular auditda ham bo'lardi, lekin Boshliq tasdiqlash oynasida
buni DARHOL ko'rishi kerak — audit jurnalini qidirmasin.

MAVJUD MA'LUMOT: `approved` holatidagi eski davrlar tegilmaydi. Ular
qulflangan va yangi bosqich ularga qo'llanmaydi (qayta ochilsa, oddiy
oqim bo'yicha yana o'tadi).

Revision ID: a9b0c1d2e3f4
Revises: f8a9b0c1d2e3
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a9b0c1d2e3f4"
down_revision: Union[str, None] = "f8a9b0c1d2e3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # batch_alter_table — SQLite ustun qo'shishda jadvalni qayta quradi;
    # PostgreSQL'da oddiy ALTER bo'lib ketadi (lokal dev SQLite'da).
    with op.batch_alter_table("payroll_periods") as batch:
        batch.add_column(sa.Column("hr_approved_by", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("hr_approved_at", sa.DateTime(), nullable=True))
        batch.create_foreign_key(
            "fk_payroll_periods_hr_approved_by", "users", ["hr_approved_by"], ["id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("payroll_periods") as batch:
        batch.drop_constraint("fk_payroll_periods_hr_approved_by", type_="foreignkey")
        batch.drop_column("hr_approved_at")
        batch.drop_column("hr_approved_by")
