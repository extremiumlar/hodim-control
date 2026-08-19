"""background_jobs — og'ir ishlar navbati (yangi TZ 2.2 / S-07)

Revision ID: u0v1w2x3y4z5
Revises: t9u0v1w2x3y4
Create Date: 2026-08-19

NEGA: cPanel Passenger'da konkurentlik = 1. Excel eksporti so'rov ichida
bajarilgani uchun yagona ishchi shu vaqt band bo'lib, BUTUN sayt navbatga
tushardi. Endi og'ir ish navbatga qo'yiladi va cron JARAYONIDA bajariladi.

Holat faqat shu jadvalda: cron har daqiqada yangi jarayon ko'taradi,
ya'ni xotiradagi navbat ishlamaydi.
"""
from alembic import op
import sqlalchemy as sa

revision = "u0v1w2x3y4z5"
down_revision = "t9u0v1w2x3y4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "background_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("params", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(10), nullable=False, server_default="queued"),
        # `ondelete=CASCADE` — xodim o'chirilsa uning navbatdagi ishi ham ketadi.
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True
        ),
        sa.Column("result_file_id", sa.String(300), nullable=True),
        sa.Column("result_note", sa.String(300), nullable=True),
        sa.Column("error", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_background_jobs_kind", "background_jobs", ["kind"])
    # Navbatdan olish so'rovi AYNAN shu ustun bo'yicha filtrlaydi.
    op.create_index("ix_background_jobs_status", "background_jobs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_background_jobs_status", table_name="background_jobs")
    op.drop_index("ix_background_jobs_kind", table_name="background_jobs")
    op.drop_table("background_jobs")
