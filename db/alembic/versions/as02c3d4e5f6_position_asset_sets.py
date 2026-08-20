"""position_asset_sets — lavozimga standart mol-mulk to'plami (TZ 3.11 / S-19)

Revision ID: as02c3d4e5f6
Revises: av04d4e5f6a7
Create Date: 2026-08-20

Jadval BUYUMNI emas, TURNI belgilaydi: «sotuvchiga 1 ta noutbuk, 1 ta
telefon, 1 ta SIM». Aniq inventar raqamni HR biriktirish paytida
tanlaydi. `UNIQUE(position_id, kind)` — bir lavozimda bir tur ikki marta
yozilmasin (miqdor `quantity` da).
"""
from alembic import op
import sqlalchemy as sa

revision = "as02c3d4e5f6"
down_revision = "av04d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "position_asset_sets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("position_id", sa.Integer(), sa.ForeignKey("positions.id"), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("note", sa.String(300), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("position_id", "kind", name="uq_position_asset_kind"),
    )
    op.create_index("ix_position_asset_sets_position_id", "position_asset_sets", ["position_id"])


def downgrade() -> None:
    op.drop_index("ix_position_asset_sets_position_id", table_name="position_asset_sets")
    op.drop_table("position_asset_sets")
