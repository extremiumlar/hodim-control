"""Mobil ilova kirishiga juftlik kodi (pairing code).

XAVFSIZLIK TUZATISHI: ilgari bot `applogin_<token>` deep-link ochilishi bilan
hech narsa so'ramasdan tasdiqlardi. `/auth/app-login/start` esa
autentifikatsiyasiz — ya'ni hujumchi o'zi havola yasab, uni xodimga
yuborardi; xodim BIR MARTA bosishi bilan hujumchi `/auth/app-login/poll`
orqali o'sha xodimning 30 kunlik JWT'sini olardi.

Endi ilova 4 xonali kod ko'rsatadi va foydalanuvchi uni BOTGA yozadi —
tasdiqlovchi odam haqiqatan ilova ekranini ko'rayotgani isbotlanadi.

Mavjud (eski) qatorlar uchun `pairing_code` bo'sh satr bo'ladi. Kod tomonida
bo'sh kod HECH QACHON to'g'ri deb qabul qilinmaydi (`api/routers/auth.py`),
ya'ni eskirgan tokenlar shunchaki yaroqsiz — ular baribir 5 daqiqada
o'chadi.

Revision ID: b3c4d5e6f7a8
Revises: a2b3c4d5e6f7
Create Date: 2026-08-01
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b3c4d5e6f7a8"
down_revision: Union[str, None] = "a2b3c4d5e6f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # server_default — jadvalda mavjud qatorlar bo'lishi mumkin (5 daqiqalik
    # muddatli, lekin deploy o'sha lahzaga to'g'ri kelishi mumkin).
    op.add_column(
        "app_login_tokens",
        sa.Column("pairing_code", sa.String(length=8), nullable=False, server_default=""),
    )
    op.add_column(
        "app_login_tokens",
        sa.Column("failed_attempts", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("app_login_tokens", "failed_attempts")
    op.drop_column("app_login_tokens", "pairing_code")
