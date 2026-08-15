"""payroll_periods: fon rejimidagi hisoblash holati (§4.3)

Revision ID: o4p5q6r7s8t9
Revises: n3o4p5q6r7s8
Create Date: 2026-08-15

NEGA: `POST /payroll/{period}/calculate` og'ir ish (20 xodim × ~12 SQL +
har rahbarga Telegram/FCM) so'rovning O'ZIDA bajarardi. cPanel Passenger'da
konkurentlik = 1 — ya'ni tugma bosilgan zahoti butun sayt 10-40 soniyaga
navbatga tushardi. Endi tugma faqat `calc_state='queued'` qo'yadi, og'ir
ishni cron JARAYONI bajaradi.

`server_default` ATAYLAB berilgan: mavjud qatorlar (allaqachon hisoblangan
oylar) NULL bo'lib qolsa, sahifa ularni «noma'lum holat» deb ko'rsatardi.
"""
from alembic import op
import sqlalchemy as sa

revision = "o4p5q6r7s8t9"
down_revision = "n3o4p5q6r7s8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("payroll_periods") as batch:
        batch.add_column(
            sa.Column("calc_state", sa.String(10), nullable=False, server_default="idle")
        )
        batch.add_column(sa.Column("calc_requested_by", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("calc_requested_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("calc_started_at", sa.DateTime(), nullable=True))
        batch.add_column(
            sa.Column("calc_progress", sa.Integer(), nullable=False, server_default="0")
        )
        batch.add_column(
            sa.Column("calc_total", sa.Integer(), nullable=False, server_default="0")
        )
        batch.add_column(sa.Column("calc_error", sa.String(500), nullable=True))
        batch.add_column(sa.Column("calc_user_ids", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("payroll_periods") as batch:
        for col in (
            "calc_user_ids",
            "calc_error",
            "calc_total",
            "calc_progress",
            "calc_started_at",
            "calc_requested_at",
            "calc_requested_by",
            "calc_state",
        ):
            batch.drop_column(col)
