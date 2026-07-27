"""app_login_tokens jadvali — mobil ilova deep-link + bir martalik token kirishi

Revision ID: b2c3d4e5f6a7
Revises: 26061eade58d
Create Date: 2026-07-27
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "26061eade58d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "app_login_tokens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("token", sa.String(64), nullable=False),
        sa.Column("telegram_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_app_login_tokens_token", "app_login_tokens", ["token"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_app_login_tokens_token", table_name="app_login_tokens")
    op.drop_table("app_login_tokens")
