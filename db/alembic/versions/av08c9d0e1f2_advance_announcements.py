"""advance_announcements — qo'lda e'lon qilingan avans kuni (Avans TZ, D-01)

Revision ID: av08c9d0e1f2
Revises: mg02a1b2c3d4
Create Date: 2026-08-20

Avans kuni ko'chishi mumkin (bayram, kassa kechikishi). Sozlamadagi
`advance_day` ni har safar o'zgartirish noqulay va u KEYINGI oylarga
ham ta'sir qilardi — bu esa faqat shu oyga tegishli bir martalik qaror.

Shu davr uchun e'lon bo'lsa `advance_day.tick` o'sha oyda umuman
ishlamaydi: xodim ikki marta xabar olmasin.
"""
from alembic import op
import sqlalchemy as sa

revision = "av08c9d0e1f2"
down_revision = "mg02a1b2c3d4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "advance_announcements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("period", sa.String(7), nullable=False),
        sa.Column("advance_date", sa.Date(), nullable=False),
        sa.Column("note", sa.String(500), nullable=True),
        sa.Column("sent_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("sent_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("recipients", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_advance_announcements_period", "advance_announcements", ["period"])


def downgrade() -> None:
    op.drop_index("ix_advance_announcements_period", table_name="advance_announcements")
    op.drop_table("advance_announcements")
