"""ad_spend + funnel_month — reklama xarajati va oylik farazlar (voronka 3-bosqich)

`ad_spend.channel` voronkadagi kanal nomi bilan AYNAN mos bo'lishi kerak
(CRM tegi yoki manba qiymati) — shuning uchun UNIQUE(period, channel) va
kiritish sahifasi nomni ro'yxatdan tanlatadi.

`funnel_month.avg_deal_profit` — ROMI uchun yagona kirish: daromad CRM'da
yo'q (lid `balance` maydoni jonli bazada deyarli doim 0), shuning uchun
rahbar bitta shartnomadan o'rtacha foydani o'zi kiritadi. Kiritilmasa ROMI
umuman ko'rsatilmaydi.

Revision ID: p5q6r7s8t9u0
Revises: o4p5q6r7s8t9
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "p5q6r7s8t9u0"
down_revision: Union[str, None] = "o4p5q6r7s8t9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ad_spend",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("period", sa.String(length=7), nullable=False),
        sa.Column("channel", sa.String(length=120), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("reach", sa.Integer(), nullable=True),
        sa.Column("note", sa.String(length=255), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("period", "channel", name="uq_ad_spend_period_channel"),
    )
    op.create_index("ix_ad_spend_period", "ad_spend", ["period"])

    op.create_table(
        "funnel_month",
        sa.Column("period", sa.String(length=7), primary_key=True),
        sa.Column("avg_deal_profit", sa.Numeric(14, 2), nullable=True),
        sa.Column("note", sa.String(length=255), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("funnel_month")
    op.drop_index("ix_ad_spend_period", table_name="ad_spend")
    op.drop_table("ad_spend")
