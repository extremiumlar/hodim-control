"""Telegram login xavfsizligi — replay himoyasi, rate-limit, invite muddati

Revision ID: c1d2e3f4a5b6
Revises: b2c3d4e5f6a7
Create Date: 2026-07-30
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c1d2e3f4a5b6"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Layer 1: Telegram Login Widget hash'ini qayta ishlatish (replay) himoyasi.
    op.create_table(
        "used_telegram_login_hashes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("hash", sa.String(64), nullable=False),
        sa.Column("consumed_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "ix_used_telegram_login_hashes_hash", "used_telegram_login_hashes", ["hash"], unique=True
    )

    # Layer 2: parolsiz kirish endpointlariga DoS/resurs himoyasi (sliding-window).
    op.create_table(
        "login_attempts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("endpoint", sa.String(40), nullable=False),
        sa.Column("identifier", sa.String(80), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_login_attempts_endpoint", "login_attempts", ["endpoint"])
    op.create_index("ix_login_attempts_identifier", "login_attempts", ["identifier"])
    op.create_index("ix_login_attempts_created_at", "login_attempts", ["created_at"])

    # Layer 3: taklif havolasi (invite_token) muddati — NULL bo'lsa (eski,
    # migratsiyadan oldingi qatorlar) muddatsiz qoladi, orqaga moslik uchun.
    op.add_column("users", sa.Column("invite_expires_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "invite_expires_at")
    op.drop_index("ix_login_attempts_created_at", table_name="login_attempts")
    op.drop_index("ix_login_attempts_identifier", table_name="login_attempts")
    op.drop_index("ix_login_attempts_endpoint", table_name="login_attempts")
    op.drop_table("login_attempts")
    op.drop_index("ix_used_telegram_login_hashes_hash", table_name="used_telegram_login_hashes")
    op.drop_table("used_telegram_login_hashes")
