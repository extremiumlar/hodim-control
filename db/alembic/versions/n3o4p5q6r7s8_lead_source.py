"""crm_lead_state: tags / source / source_checked_at — lid manbai (voronka 2-bosqich)

IKKI SIGNAL, IKKI NARX:
- `tags` — CRM teglari, ommaviy `/lead/filter` javobida BEPUL keladi
  (jonli namunada: #telegram, #incominglids, #outgoinglids, #missedcalls va
  kampaniya teglari «#Webinar_15_aprel» kabi). Kanal kesimidagi voronkaning
  asosiy manbai shu.
- `source` — attribution kanali (`MOI_ZVONKI`, `FACEBOOK_FORM`...). Ommaviy
  javobda YO'Q, faqat `GET /lead/{id}` da — ya'ni HAR LID uchun alohida
  so'rov. Uysot limiti 60 so'rov/daqiqa va u boshqa ishlar bilan
  bo'lishiladi, shuning uchun byudjetli boyituvchi sekin to'ldiradi.
  `source_checked_at` — qayta so'ramaslik izi (manba topilmasa ham qo'yiladi).

Revision ID: n3o4p5q6r7s8
Revises: m2n3o4p5q6r7
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "n3o4p5q6r7s8"
down_revision: Union[str, None] = "m2n3o4p5q6r7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("crm_lead_state") as batch:
        batch.add_column(sa.Column("tags", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("source", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("source_checked_at", sa.DateTime(), nullable=True))
    op.create_index("ix_crm_lead_state_source", "crm_lead_state", ["source"])


def downgrade() -> None:
    op.drop_index("ix_crm_lead_state_source", table_name="crm_lead_state")
    with op.batch_alter_table("crm_lead_state") as batch:
        batch.drop_column("source_checked_at")
        batch.drop_column("source")
        batch.drop_column("tags")
