"""users.can_edit_attendance — davomat vaqtini tuzatish huquqi (shaxsan beriladi)

Roldan qat'i nazar ayrim odamlarga beriladigan ruxsat: egasi "ma'lum bir
odamlarga" davomat keldi/ketdi vaqtini tuzatish huquqini berishni so'radi.
Yangi ROL yaratilmadi — aks holda o'sha odam boshqa hamma joyda (norma,
oylik, statistika) ham yangi rol huquqlarini olib qolardi.

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-08-03
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c4d5e6f7a8b9"
down_revision: Union[str, None] = "b3c4d5e6f7a8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # server_default="0" — mavjud qatorlar uchun NOT NULL ni ta'minlaydi
    # (SQLite ustun qo'shishda eski qatorlarga qiymat yoza olmaydi).
    op.add_column(
        "users",
        sa.Column("can_edit_attendance", sa.Boolean(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("users", "can_edit_attendance")
