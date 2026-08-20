"""staff_positions — shtat jadvali (yangi TZ 3.20 / S-23)

Revision ID: st01f6a7b8c9
Revises: bd01e5f6a7b8
Create Date: 2026-08-20

⚠️ «BAND» SONI USTUNI YO'Q va bo'lmaydi (TZ qabul mezoni): u faol
xodimlardan HISOBLANADI. Saqlansa darhol eskirardi — xodim ishdan
bo'shaydi, shtat jadvalini yangilash unutiladi va tizim «hammasi band»
deb yolg'on ko'rsatib turaveradi.

`salary_min`/`salary_max` — INTEGER: matn bo'lsa «5-7 mln» kabi yozuvlar
paydo bo'lib, byudjet hisobi ishlamasdi.
"""
from alembic import op
import sqlalchemy as sa

revision = "st01f6a7b8c9"
down_revision = "bd01e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "staff_positions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("department", sa.String(120), nullable=False),
        sa.Column("position_id", sa.Integer(), sa.ForeignKey("positions.id"), nullable=False),
        sa.Column("units", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("salary_min", sa.Integer(), nullable=True),
        sa.Column("salary_max", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(12), nullable=False, server_default="open"),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("note", sa.String(500), nullable=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_staff_positions_department", "staff_positions", ["department"])
    op.create_index("ix_staff_positions_position_id", "staff_positions", ["position_id"])
    op.create_index("ix_staff_positions_status", "staff_positions", ["status"])
    op.create_index("ix_staff_positions_effective_from", "staff_positions", ["effective_from"])


def downgrade() -> None:
    op.drop_index("ix_staff_positions_effective_from", table_name="staff_positions")
    op.drop_index("ix_staff_positions_status", table_name="staff_positions")
    op.drop_index("ix_staff_positions_position_id", table_name="staff_positions")
    op.drop_index("ix_staff_positions_department", table_name="staff_positions")
    op.drop_table("staff_positions")
