"""outbox — chiquvchi xabarlar navbati (Avans TZ, B-03)

Revision ID: av06a7b8c9d0
Revises: mg01f6a7b8c9
Create Date: 2026-08-20

Xabarlar hozir SO'ROV ICHIDA yuboriladi: Telegram sekinlashsa yoki 429
bersa foydalanuvchi so'rovi o'sha yerda kutadi (cPanel'da konkurentlik
1 — bitta sekin xabar butun saytni qotiradi). Navbat orqali so'rov
xabarni bazaga yozadi va darhol javob qaytaradi.

`dedupe_key` UNIQUE — «bir xabar ikki marta yuborilmasin» kafolati.
`claimed_by` — ikki cron jarayoni bitta xabarni olmasligi uchun.
"""
from alembic import op
import sqlalchemy as sa

revision = "av06a7b8c9d0"
down_revision = "mg01f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "outbox",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(10), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.String(500), nullable=True),
        sa.Column("scheduled_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
        sa.Column("claimed_by", sa.String(40), nullable=True),
        sa.Column("claimed_at", sa.DateTime(), nullable=True),
        sa.Column("dedupe_key", sa.String(120), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_outbox_chat_id", "outbox", ["chat_id"])
    op.create_index("ix_outbox_kind", "outbox", ["kind"])
    op.create_index("ix_outbox_status", "outbox", ["status"])
    op.create_index("ix_outbox_scheduled_at", "outbox", ["scheduled_at"])
    op.create_index("ix_outbox_claimed_by", "outbox", ["claimed_by"])
    op.create_index("uq_outbox_dedupe_key", "outbox", ["dedupe_key"], unique=True)


def downgrade() -> None:
    op.drop_index("uq_outbox_dedupe_key", table_name="outbox")
    op.drop_index("ix_outbox_claimed_by", table_name="outbox")
    op.drop_index("ix_outbox_scheduled_at", table_name="outbox")
    op.drop_index("ix_outbox_status", table_name="outbox")
    op.drop_index("ix_outbox_kind", table_name="outbox")
    op.drop_index("ix_outbox_chat_id", table_name="outbox")
    op.drop_table("outbox")
