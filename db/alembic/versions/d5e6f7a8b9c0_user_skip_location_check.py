"""users.skip_location_check — joylashuvsiz check-in ruxsati

Doimiy ob'ektda yurmaydigan xodimlar (mobilograf, kuryer, ko'chma sotuv)
ofis radiusidan tashqarida ishlaydi va GPS tekshiruvi ularni doim bloklardi.
Face ID bekor qilinmaydi — faqat GPS chetlab o'tiladi.

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-08-03
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d5e6f7a8b9c0"
down_revision: Union[str, None] = "c4d5e6f7a8b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("skip_location_check", sa.Boolean(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("users", "skip_location_check")
