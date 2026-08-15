"""crm_lead_state.crm_created_ts — voronka kogortasi uchun

Lidning CRM'DA yaratilgan vaqti. Kogorta («avgustda kelgan lidlarning nechtasi
sotildi») aynan shunga tayanadi — bizning skanerimiz lidni qachon ko'rgani
(`first_seen_at`) emas: skaner 2026-07-22 da ishga tushgan va o'sha kuni
mavjud bo'lgan BARCHA lidlar bitta kunga to'planib qolgan.

Eski qatorlarda NULL qoladi (CRM'dan qayta so'rovsiz to'ldirib bo'lmaydi) —
hisobda `COALESCE(crm_created_ts, first_seen_at)` ishlatiladi va bunday
kogortalar «taxminiy» deb belgilanadi.

BU MIGRATSIYA IKKI BOSHOQNI BIRLASHTIRADI (merge): `k0l1m2n3o4p5` (guruh
digestidagi shartnoma) va `l1m2n3o4p5q6` (ariza siyosatlari) bir vaqtda
yozilib, daraja ikkiga bo'lingan edi — shundan buyon serverda `alembic
upgrade head` xato berardi va `heads` (ko'plik) ishlatishga to'g'ri kelardi.
Shu yerdan keyin yana bitta chiziq.

Revision ID: m2n3o4p5q6r7
Revises: k0l1m2n3o4p5, l1m2n3o4p5q6
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "m2n3o4p5q6r7"
down_revision: Union[str, Sequence[str], None] = ("k0l1m2n3o4p5", "l1m2n3o4p5q6")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("crm_lead_state") as batch:
        batch.add_column(sa.Column("crm_created_ts", sa.Integer(), nullable=True))
    op.create_index(
        "ix_crm_lead_state_crm_created_ts", "crm_lead_state", ["crm_created_ts"]
    )


def downgrade() -> None:
    op.drop_index("ix_crm_lead_state_crm_created_ts", table_name="crm_lead_state")
    with op.batch_alter_table("crm_lead_state") as batch:
        batch.drop_column("crm_created_ts")
