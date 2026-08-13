"""appeals: e'tiroz va shikoyatlar bo'limi

Egasining talabi (2026-08-13): xodim jarima/davomat/oylik bo'yicha rasmiy
e'tiroz bildira olsin, umumiy shikoyat ham yubora olsin; HR/Boshliq izli
(auditli) qaror qilsin (KUNDALIK_ETIROZ_REJASI.md, Bosqich 4).

Nega bitta jadval (ikkita emas): e'tiroz va shikoyatning HAYOT SIKLI bir xil
(kelib tushdi → o'rganilmoqda → qaror + izoh), farqi faqat `kind` va manzil
maydonlarida (`ref_date`/`ref_period`). Ikkita jadval bo'lsa SLA tick'i,
maxfiylik filtri va audit yozuvlari ikki nusxada takrorlanardi.

⚠️ Bu jadval HECH NARSANI HISOBLAMAYDI: e'tiroz qondirilganda davomat/pul
tuzatish faqat MAVJUD mexanizmlar orqali (ExcusedDay, PayrollAdjustment) —
`explanation_requests` da isbotlangan tamoyil. Shuning uchun bu yerda hech
qanday summa/status ustuni yo'q.

`sla_reminded_at` / `escalated_at` — eslatma va eskalatsiya bir marta ketishi
uchun IZ ustunlari (production cPanel'da cron ikki jarayonda ishlashi mumkin,
alohida jadval ochish shart emas).

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e4f5a6b7c8d9"
down_revision: Union[str, None] = "d3e4f5a6b7c8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "appeals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("kind", sa.String(length=12), nullable=False),
        sa.Column("topic", sa.String(length=12), nullable=False, server_default="other"),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("is_anonymous", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("recipient_role", sa.String(length=10), nullable=False, server_default="hr"),
        sa.Column("ref_date", sa.Date(), nullable=True),
        sa.Column("ref_period", sa.String(length=7), nullable=True),
        sa.Column("file_id", sa.String(length=200), nullable=True),
        sa.Column("file_type", sa.String(length=20), nullable=True),
        sa.Column("status", sa.String(length=12), nullable=False, server_default="pending"),
        sa.Column("review_started_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("review_started_at", sa.DateTime(), nullable=True),
        sa.Column("decided_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.Column("sla_reminded_at", sa.DateTime(), nullable=True),
        sa.Column("escalated_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_appeals_user_id", "appeals", ["user_id"])
    op.create_index("ix_appeals_kind", "appeals", ["kind"])
    op.create_index("ix_appeals_status", "appeals", ["status"])
    op.create_index("ix_appeals_created_at", "appeals", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_appeals_created_at", table_name="appeals")
    op.drop_index("ix_appeals_status", table_name="appeals")
    op.drop_index("ix_appeals_kind", table_name="appeals")
    op.drop_index("ix_appeals_user_id", table_name="appeals")
    op.drop_table("appeals")
