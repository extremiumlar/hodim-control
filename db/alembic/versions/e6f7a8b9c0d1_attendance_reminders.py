"""attendance_reminders — «Keldim/Ketdim bosishni unutmang» eslatmasi izi

Eslatma tick'i har ~5 daqiqada ishlaydi, ya'ni "ish boshlanishiga 15 daqiqa
qoldi" sharti bir necha marta rost bo'ladi. Iz bo'lmasa xodim bir ertalabda
3-4 marta bir xil xabar olardi.

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
Create Date: 2026-08-03
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e6f7a8b9c0d1"
down_revision: Union[str, None] = "d5e6f7a8b9c0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "attendance_reminders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("sent_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        # Takror yuborishning ASOSIY qo'riqchisi — poyga holatida ham ishlaydi
        # (ikki tick bir vaqtda kelsa, ikkinchisi IntegrityError oladi).
        sa.UniqueConstraint("user_id", "date", "kind", name="uq_att_reminder_user_date_kind"),
    )
    op.create_index("ix_attendance_reminders_user_id", "attendance_reminders", ["user_id"])
    op.create_index("ix_attendance_reminders_date", "attendance_reminders", ["date"])


def downgrade() -> None:
    op.drop_index("ix_attendance_reminders_date", table_name="attendance_reminders")
    op.drop_index("ix_attendance_reminders_user_id", table_name="attendance_reminders")
    op.drop_table("attendance_reminders")
