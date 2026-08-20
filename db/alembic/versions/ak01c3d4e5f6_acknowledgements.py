"""acknowledgements — umumiy «Tanishdim» qaydi (yangi TZ / S-20)

Revision ID: ak01c3d4e5f6
Revises: av06a7b8c9d0
Create Date: 2026-08-20

Uchta modul (yo'riqnoma 3.16, e'lon 3.12, instruktaj 3.6) bitta jadvalga
yozadi. `UNIQUE(user_id, object_type, object_id, version)` — bir odam bir
versiyani ikki marta tasdiqlay olmaydi (TZ qabul mezoni), va bu BAZA
darajasida: takroriy so'rov ikkinchi qator yaratmaydi.
"""
from alembic import op
import sqlalchemy as sa

revision = "ak01c3d4e5f6"
down_revision = "av06a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "acknowledgements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("object_type", sa.String(16), nullable=False),
        sa.Column("object_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("title", sa.String(300), nullable=True),
        sa.Column("link", sa.String(300), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(), nullable=True),
        sa.Column("requested_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("requested_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.UniqueConstraint(
            "user_id", "object_type", "object_id", "version",
            name="uq_ack_user_object_version",
        ),
    )
    op.create_index("ix_acknowledgements_user_id", "acknowledgements", ["user_id"])
    op.create_index("ix_acknowledgements_object_type", "acknowledgements", ["object_type"])
    op.create_index("ix_acknowledgements_object_id", "acknowledgements", ["object_id"])
    # `pending_for(user)` shu indeksdan foydalanadi — u har sahifa
    # yuklanishida chaqiriladi (kabinetdagi «tanishmagan» belgisi).
    op.create_index(
        "ix_acknowledgements_acknowledged_at", "acknowledgements", ["acknowledged_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_acknowledgements_acknowledged_at", table_name="acknowledgements")
    op.drop_index("ix_acknowledgements_object_id", table_name="acknowledgements")
    op.drop_index("ix_acknowledgements_object_type", table_name="acknowledgements")
    op.drop_index("ix_acknowledgements_user_id", table_name="acknowledgements")
    op.drop_table("acknowledgements")
