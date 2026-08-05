"""Eslatma nuqtalari (10/5/0 daq) + digest vaqtlari 10:05 / 22:30

Ikki o'zgarish, ikkalasi ham egasining 2026-08-04 talabidan:

1) `attendance_reminders.kind` endi "check_in_10" / "check_out_0" ko'rinishida
   — eslatma bir marta emas, UCH nuqtada yuboriladi. Eski VARCHAR(10) ga
   "check_out_10" (12 belgi) SIG'MAYDI. PostgreSQL buni rad etadi
   (StringDataRightTruncation), SQLite esa jimgina qabul qilaverardi — ya'ni
   lokalda ishlab, jonli serverda sinar edi.

   Eski izlar ("check_in" / "check_out") O'CHIRILADI: ular yangi sxemada
   qaysi nuqtaga tegishli ekani noma'lum va qolsa, bugungi "check_in_10"
   yuborilishiga to'sqinlik qilmaydi-yu, lekin hisobotda chalkash ko'rinardi.
   Yo'qotiladigan narsa yo'q — bu faqat "yuborildi" izi.

2) Guruh digesti vaqti: ertalab 09:30 -> 10:05, kechqurun 22:00 -> 22:30.
   DIQQAT: kechki vaqt shunchaki xabar emas — `write_absent_records` va
   tushuntirish xatlari ham AYNI shu nuqtada ishga tushadi ("kun tugadi"),
   ya'ni ular ham yarim soat kechroq boshlanadi.

Revision ID: c5d6e7f8a9b0
Revises: b4c5d6e7f8a9
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c5d6e7f8a9b0"
down_revision: Union[str, None] = "b4c5d6e7f8a9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Eski izlarni tozalaymiz (yuqoridagi izohga qarang) — ustunni
    # kengaytirishdan OLDIN, aks holda keraksiz qatorlar ko'chib yurardi.
    op.execute("DELETE FROM attendance_reminders WHERE kind IN ('check_in', 'check_out')")

    # batch_alter_table — SQLite ustun tipini joyida o'zgartira olmaydi
    # (jadvalni qayta quradi); PostgreSQL'da oddiy ALTER bo'lib ketadi.
    with op.batch_alter_table("attendance_reminders") as batch:
        batch.alter_column(
            "kind",
            existing_type=sa.String(length=10),
            type_=sa.String(length=20),
            existing_nullable=False,
        )

    op.execute(
        "UPDATE attendance_digest_config "
        "SET morning_hour = 10, morning_minute = 5, evening_hour = 22, evening_minute = 30 "
        "WHERE id = 1"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE attendance_digest_config "
        "SET morning_hour = 9, morning_minute = 30, evening_hour = 22, evening_minute = 0 "
        "WHERE id = 1"
    )
    # Uzun `kind` qiymatlari qisqa ustunga sig'maydi — qaytishdan oldin
    # o'chirilishi SHART, aks holda ALTER xato beradi.
    op.execute("DELETE FROM attendance_reminders WHERE length(kind) > 10")
    with op.batch_alter_table("attendance_reminders") as batch:
        batch.alter_column(
            "kind",
            existing_type=sa.String(length=20),
            type_=sa.String(length=10),
            existing_nullable=False,
        )
