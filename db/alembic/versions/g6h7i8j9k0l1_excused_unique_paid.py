"""excused_days: UNIQUE(user_id, date) + is_paid

ARIZALAR_REJASI.md Bosqich 0.1 va 0.3 — ariza modulidan OLDIN yopilishi
shart bo'lgan ikki teshik.

1) UNIQUE(user_id, date). Ilgari cheklov faqat KODDA edi (`excused_days.py`
   dublikatni qo'lda tekshiradi) — bu bitta so'rov uchun yetarli, lekin
   ta'til arizasi oraliqdagi 10 kunni birvarakayiga yozadi va poyga
   holatida (takroriy tasdiq, ikki HR) dublikat paydo bo'lardi: sababli kun
   ikki marta hisoblanib, oylikka ta'sir qilardi.
   Jadvalda `Bonus`, `Attendance`, `WorkScheduleWeekly/Override` da bunday
   cheklov allaqachon bor — `excused_days` ataylab emas, e'tibordan
   chetda qolgan.

   Migratsiya avval MAVJUD dublikatlarni tozalaydi. Saqlash tartibi:
   `approved` > `pending` > `rejected`, teng bo'lsa eng katta `id` (eng
   oxirgi qaror). Jonli bazada (2026-08-13) dublikat YO'Q edi — tozalash
   faqat xavfsizlik to'ri va lokal/eski nusxalar uchun.

2) `is_paid` (default TRUE — bugungi xatti-harakat o'zgarmaydi).
   Hozir `monthly` stavkada HAR QANDAY sababli kun to'liq to'lanadi
   (`payroll.compute_base` docstringi), `daily`/`hourly` da esa hech qachon.
   Ya'ni «o'z hisobidan ta'til» oyliklilarga bepul dam bo'lib qolardi.
   Eski Django tizimida bu ajratilgan edi (`verifix/backend/payroll/
   services.py:37-38`).

Revision ID: g6h7i8j9k0l1
Revises: f5a6b7c8d9e0
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "g6h7i8j9k0l1"
down_revision: Union[str, None] = "f5a6b7c8d9e0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── 1. Dublikatlarni tozalash (UNIQUE qo'yishdan OLDIN) ──
    # Har (user_id, date) juftligida bitta qator qoldiriladi. Tartib:
    # approved(2) > pending(1) > rejected(0), teng bo'lsa katta id.
    # DIQQAT: `DELETE ... USING` PostgreSQL sintaksisi, SQLite'da yo'q —
    # shuning uchun ikkala bazada ham ishlaydigan `IN (subquery)` shakli.
    op.execute(
        """
        DELETE FROM excused_days
        WHERE id NOT IN (
            SELECT keep_id FROM (
                SELECT id AS keep_id,
                       ROW_NUMBER() OVER (
                           PARTITION BY user_id, date
                           ORDER BY CASE status
                                        WHEN 'approved' THEN 2
                                        WHEN 'pending'  THEN 1
                                        ELSE 0
                                    END DESC,
                                    id DESC
                       ) AS rn
                FROM excused_days
            ) ranked
            WHERE rn = 1
        )
        """
    )

    # ── 2. is_paid + UNIQUE ──
    # batch_alter_table — SQLite ustun/cheklov qo'shishda jadvalni qayta
    # quradi; PostgreSQL'da (production) oddiy ALTER bo'lib ketadi.
    with op.batch_alter_table("excused_days") as batch:
        batch.add_column(
            sa.Column("is_paid", sa.Boolean(), nullable=False, server_default=sa.true())
        )
        batch.create_unique_constraint("uq_excused_day_user_date", ["user_id", "date"])


def downgrade() -> None:
    with op.batch_alter_table("excused_days") as batch:
        batch.drop_constraint("uq_excused_day_user_date", type_="unique")
        batch.drop_column("is_paid")
