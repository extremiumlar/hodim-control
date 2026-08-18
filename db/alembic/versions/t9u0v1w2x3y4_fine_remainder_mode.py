"""Ushlanma avval BONUSDAN + qoldiq qoidasi (yangi TZ 2.1 / S-02)

Revision ID: t9u0v1w2x3y4
Revises: s8t9u0v1w2x3
Create Date: 2026-08-18

NEGA (HUQUQIY XAVF): `fine_applies_to` default `net_salary` edi — ushlanma
to'g'ridan-to'g'ri ish haqidan olinardi. TZ bo'yicha bu O'zbekiston Mehnat
kodeksiga zid va tekshiruvda birinchi topiladigan xato. Endi default
`bonus_first`: avval bonus (rag'bat to'lovi) kamaytiriladi.

Bonus ushlanmadan KAM bo'lsa qoldiq nima bo'ladi — bu BIZNES qarori va
vaqt o'tib o'zgarishi mumkin, shuning uchun kodda qotirilmaydi:
`fine_remainder_mode` (drop | carry_next_month | from_salary), default
`drop` — ish haqiga umuman tegilmaydi.

MAVJUD QATORLAR HAM KO'CHIRILADI — aks holda huquqiy xavf o'zgarmay
qolardi (yangi qoida faqat kelajakda yaratiladigan qatorlarga tegishli
bo'lib qolardi, jonli bazada esa qoida atigi bitta).

⚠️ ESKI PAYSLIP'LARGA TEGILMAYDI. Payslip `breakdown` da qoida SNAPSHOT
qilingan va bu migratsiya hisobni qayta yurgizmaydi. Yangi qoida faqat
KEYINGI hisoblashdan kuchga kiradi.
"""
from alembic import op
import sqlalchemy as sa

revision = "t9u0v1w2x3y4"
down_revision = "s8t9u0v1w2x3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("fine_policies") as batch:
        batch.add_column(
            sa.Column(
                "fine_remainder_mode", sa.String(20), nullable=False, server_default="drop"
            )
        )

    # Mavjud qoidalarni yangi (xavfsiz) rejimga ko'chiramiz.
    op.execute(
        "UPDATE fine_policies SET fine_applies_to = 'bonus_first' "
        "WHERE fine_applies_to = 'net_salary'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE fine_policies SET fine_applies_to = 'net_salary' "
        "WHERE fine_applies_to = 'bonus_first'"
    )
    with op.batch_alter_table("fine_policies") as batch:
        batch.drop_column("fine_remainder_mode")
