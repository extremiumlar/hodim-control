"""funnel_month: target_contracts + assumptions — teskari kalkulyator (4-bosqich)

`target_contracts` — oylik maqsad («10 uy»). `assumptions` — rahbar qo'lda
o'zgartirgan farazlar (konversiya foizlari, CPL). ATAYLAB «ustiga yozish»
qatlami: faqat o'zgartirilgan kalitlar saqlanadi, qolgani o'lchangan
qiymatdan olinadi — shunda o'lchov yangilanganda reja ham yangilanadi va
eskirgan nusxa qotib qolmaydi.

Revision ID: q6r7s8t9u0v1
Revises: p5q6r7s8t9u0
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "q6r7s8t9u0v1"
down_revision: Union[str, None] = "p5q6r7s8t9u0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("funnel_month") as batch:
        batch.add_column(sa.Column("target_contracts", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("assumptions", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("funnel_month") as batch:
        batch.drop_column("assumptions")
        batch.drop_column("target_contracts")
