"""davr yopilganda pending avans qoidasi (Avans TZ, A-06)

Revision ID: av04d4e5f6a7
Revises: av03c3d4e5f6
Create Date: 2026-08-20

`fine_policies.advance_pending_on_close` — davr qulflanganda hali
tasdiqlanmagan avans nima bo'ladi: `carry` (keyingi davrga o'tadi,
DEFAULT) yoki `cancel` (avtomatik rad etiladi).

DEFAULT `carry` ataylab: pul so'ragan odam javobsiz qolmasin. Davr
yopilishi — hisob-kitob chegarasi, so'rovning taqdiri emas. Ilgari
bunday qoida umuman yo'q edi va `pending` avans qulflangan davrda
abadiy osilib qolardi: oylikka ham kirmasdi, rad ham etilmasdi.
"""
from alembic import op
import sqlalchemy as sa

revision = "av04d4e5f6a7"
down_revision = "av03c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("fine_policies") as batch:
        batch.add_column(
            sa.Column(
                "advance_pending_on_close",
                sa.String(10),
                nullable=False,
                server_default="carry",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("fine_policies") as batch:
        batch.drop_column("advance_pending_on_close")
