"""users.can_edit_fine_policy — kechikish/jarima qoidasini o'zgartirish huquqi

Roldan mustaqil, shaxsan beriladi. Beruvchi: Dasturchi YOKI Boshliq.
FAQAT `FinePolicy` endpointlarini ochadi — oylik hisoblash/tasdiqlash va
stavkalar `_require_manage` da qoladi.

Revision ID: f7a8b9c0d1e3
Revises: e6f7a8b9c0d1
Create Date: 2026-08-03
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f7a8b9c0d1e3"
down_revision: Union[str, None] = "e6f7a8b9c0d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("can_edit_fine_policy", sa.Boolean(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("users", "can_edit_fine_policy")
