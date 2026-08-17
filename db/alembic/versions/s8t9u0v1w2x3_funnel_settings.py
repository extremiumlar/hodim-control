"""funnel_settings — voronka qoidalari panelda boshqariladi

TZ ning 0-bosqichida «bekor qilingan shartnoma va sifatsiz lid qanday
sanaladi» degan ta'rif talab qilingan edi, lekin u ochiq qolgandi. Endi
javob kodda emas, PANELDA: rahbar ikkala qoidani ham yoqib-o'chiradi va
qaysi CRM bosqichlari «bekor»/«sifatsiz» ekanini o'zi belgilaydi.

Default — IKKALASI HAM O'CHIQ: mavjud raqamlar birdan o'zgarib ketmasin
(rahbar ongli ravishda yoqsin).

Revision ID: s8t9u0v1w2x3
Revises: q6r7s8t9u0v1, r7s8t9u0v1w2

⚠️ MERGE: parallel ish (qo'shimcha ish global profili) bilan bir vaqtda
yozilgani uchun daraxt yana ikkiga bo'lingan edi — shu yerda birlashadi.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "s8t9u0v1w2x3"
down_revision: Union[str, Sequence[str], None] = ("q6r7s8t9u0v1", "r7s8t9u0v1w2")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "funnel_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("cancelled_pipe_status_ids", sa.JSON(), nullable=True),
        sa.Column("subtract_cancelled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("low_quality_pipe_status_ids", sa.JSON(), nullable=True),
        sa.Column("exclude_low_quality", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("funnel_settings")
