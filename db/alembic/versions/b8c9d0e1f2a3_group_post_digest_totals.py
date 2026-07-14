"""group_post_config: digest paytidagi jami raqamlar + tuzatish qo'riqchisi

Kechqurungi digest yuborilganda ko'rsatilgan jami (qo'ng'iroq/lid/tashrif)
saqlanadi; ertasi 09:00 dagi "kecha yakuni" tuzatish xabari yakuniy (muzlatilgan)
raqamlarni shu bilan solishtiradi. correction_last_posted — bir kunda bir marta.

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-07-14
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b8c9d0e1f2a3"
down_revision: Union[str, None] = "a7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("group_post_config", sa.Column("last_posted_calls", sa.Integer(), nullable=True))
    op.add_column("group_post_config", sa.Column("last_posted_leads", sa.Integer(), nullable=True))
    op.add_column("group_post_config", sa.Column("last_posted_visits", sa.Integer(), nullable=True))
    op.add_column("group_post_config", sa.Column("correction_last_posted", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("group_post_config", "correction_last_posted")
    op.drop_column("group_post_config", "last_posted_visits")
    op.drop_column("group_post_config", "last_posted_leads")
    op.drop_column("group_post_config", "last_posted_calls")
