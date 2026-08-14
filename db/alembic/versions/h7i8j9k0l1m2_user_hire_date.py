"""users.hire_date — ishga kirgan sana

ARIZALAR_REJASI.md Bosqich 0: ta'til stajini/balansini hisoblash uchun
haqiqiy ishga kirish sanasi kerak. `created_at` bu vazifani bajara olmaydi —
u tizimga qo'shilgan payt (xodim allaqachon bir yil ishlagan bo'lishi mumkin).

TO'LDIRISH: mavjud xodimlarga `salary_rates.effective_from` ning eng
kichigidan qo'yiladi. Nega aynan u: payroll allaqachon shu sanani de-fakto
"ish boshlangan kun" sifatida ishlatadi — oy o'rtasida boshlangan stavka
uchun asosiy oylikni prorata qiladi (`api/services/payroll.py: compute_base`,
`first_rate.effective_from`). Ya'ni yangi ustun mavjud mantiq bilan mos
bo'ladi, yangi haqiqat o'ylab topilmaydi.

Yumshoq o'chirilgan stavkalar (`deleted_at IS NOT NULL`) hisobga OLINMAYDI —
ular xato kiritilgan yozuvlar. Stavkasi umuman yo'q xodimlarda NULL qoladi
(HR keyin qo'lda kiritadi).

Revision ID: h7i8j9k0l1m2
Revises: g6h7i8j9k0l1
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "h7i8j9k0l1m2"
down_revision: Union[str, None] = "g6h7i8j9k0l1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("hire_date", sa.Date(), nullable=True))

    # Korrelyatsiyalangan subquery — SQLite va PostgreSQL ikkalasida ham
    # bir xil ishlaydi (`UPDATE ... FROM` esa faqat Postgres'da).
    op.execute(
        """
        UPDATE users
        SET hire_date = (
            SELECT MIN(sr.effective_from)
            FROM salary_rates sr
            WHERE sr.user_id = users.id AND sr.deleted_at IS NULL
        )
        WHERE hire_date IS NULL
        """
    )


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_column("hire_date")
