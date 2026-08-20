"""advance_responses — avans kuni xabariga munosabat (Avans TZ, C bloki)

Revision ID: av07b8c9d0e1
Revises: av06a7b8c9d0
Create Date: 2026-08-20

Bot holati aiogram FSM da saqlansa, Passenger/cPanel jarayoni qayta
ishga tushganda xodim yozayotgan summa yo'qolardi va u sababini
tushunmasdi. Bazadagi holat qayta ishga tushishdan omon qoladi.

Bitta jadval to'rt savolga javob beradi (summa kutilyaptimi · javob
berdimi · eslatma yuborilganmi · qanday summa ko'rsatilgan edi),
shuning uchun alohida `advance_pending_input` qurilmadi.
"""
from alembic import op
import sqlalchemy as sa

revision = "av07b8c9d0e1"
down_revision = "av06a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "advance_responses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("period", sa.String(7), nullable=False),
        sa.Column("state", sa.String(16), nullable=False, server_default="offered"),
        sa.Column("offered_limit", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("input_expires_at", sa.DateTime(), nullable=True),
        sa.Column("reminded_at", sa.DateTime(), nullable=True),
        sa.Column(
            "adjustment_id",
            sa.Integer(),
            sa.ForeignKey("payroll_adjustments.id"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "period", name="uq_advance_responses_user_period"),
    )
    op.create_index("ix_advance_responses_user_id", "advance_responses", ["user_id"])
    op.create_index("ix_advance_responses_period", "advance_responses", ["period"])


def downgrade() -> None:
    op.drop_index("ix_advance_responses_period", table_name="advance_responses")
    op.drop_index("ix_advance_responses_user_id", table_name="advance_responses")
    op.drop_table("advance_responses")
