"""work_log_entries: ish kundaligi — xodimning kunlik ish yozuvlari

Egasining talabi (2026-08-13): har xodim kun davomida bajargan ishlarini yozib
borsin, rahbar oy kesimida ko'rsin (KUNDALIK_ETIROZ_REJASI.md, Bosqich 1).

Nega alohida jadval (DailyResult'ga ustun emas): daily_results — kunda BITTA
qator (UNIQUE user+date) va raqamli natijalar (suhbat/tashrif soni) uchun;
kundalikda esa kun ichida BIR NECHTA erkin matnli yozuv bo'ladi va har biri
o'z vaqt tamg'asi bilan saqlanadi — oy oxirida to'qib chiqarilgan "hisobot"ning
oldini shu vaqt tamg'alari oladi.

`deleted_at` — yumshoq o'chirish (norms jadvalidagi naqsh): xodim bugungi
yozuvini o'chira oladi, lekin qator bazada qoladi (hujjatlik/audit qiymati).

Eslatma izi uchun alohida jadval YO'Q — mavjud attendance_reminders
(UNIQUE user+date+kind) ga yangi kind="work_log" qiymati ishlatiladi;
String ustunga yangi qiymat migratsiya talab qilmaydi.

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d3e4f5a6b7c8"
down_revision: Union[str, None] = "c2d3e4f5a6b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "work_log_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=10), nullable=False, server_default="bot"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_work_log_entries_user_id", "work_log_entries", ["user_id"])
    op.create_index("ix_work_log_entries_date", "work_log_entries", ["date"])


def downgrade() -> None:
    op.drop_index("ix_work_log_entries_date", table_name="work_log_entries")
    op.drop_index("ix_work_log_entries_user_id", table_name="work_log_entries")
    op.drop_table("work_log_entries")
