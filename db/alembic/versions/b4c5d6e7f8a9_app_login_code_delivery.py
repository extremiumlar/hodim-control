"""Saytdan kirishda juftlik kodi mobil ilovaga push bilan boradi.

2026-08-05 talabi: saytdagi «Bot orqali kirish»da 4 xonali kod sayt
sahifasida KO'RINMASIN — bot deep-link ochilganda kod foydalanuvchining
mobil ilovasiga push orqali yuborilsin, foydalanuvchi uni ilovadan o'qib
botga yozadi.

`code_delivery` kod qayerdan yetishini belgilaydi:
  screen — kirish boshlangan ekranda ko'rsatiladi (mobil ilova oqimi,
           hamda push imkonsiz bo'lganda saytning zaxira holati);
  push   — saytdan boshlangan kirish, kod ilovaga push bilan ketadi.

Mavjud qatorlar (5 daqiqalik tokenlar) uchun server_default "screen" —
eski xatti-harakat saqlanadi.

Revision ID: b4c5d6e7f8a9
Revises: a8b9c0d1e2f4
Create Date: 2026-08-05
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b4c5d6e7f8a9"
down_revision: Union[str, None] = "a8b9c0d1e2f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "app_login_tokens",
        sa.Column("code_delivery", sa.String(length=10), nullable=False, server_default="screen"),
    )


def downgrade() -> None:
    op.drop_column("app_login_tokens", "code_delivery")
