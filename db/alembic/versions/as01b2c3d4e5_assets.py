"""assets + asset_assignments — biriktirilgan mol-mulk (yangi TZ 3.11 / S-18)

Revision ID: as01b2c3d4e5
Revises: av02b2c3d4e5
Create Date: 2026-08-20

⚠️ QISMAN UNIKAL INDEKS: bitta buyum bir vaqtda faqat BITTA xodimda
bo'lishi kerak. Faqat kodga tayanish yetarli emas — parallel ikki so'rov
tekshiruvdan birga o'tib, ikkita ochiq biriktirish yaratishi mumkin.
Shart `returned_at IS NULL`: qaytarilgan qatorlar tarix uchun qoladi va
ularga cheklov qo'llanmaydi.
"""
from alembic import op
import sqlalchemy as sa

revision = "as01b2c3d4e5"
down_revision = "av02b2c3d4e5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "assets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("inventory_no", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("condition", sa.String(12), nullable=False, server_default="good"),
        sa.Column("value", sa.Integer(), nullable=True),
        sa.Column("note", sa.String(500), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_assets_kind", "assets", ["kind"])

    op.create_table(
        "asset_assignments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("asset_id", sa.Integer(), sa.ForeignKey("assets.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("assigned_at", sa.Date(), nullable=False),
        sa.Column("returned_at", sa.Date(), nullable=True),
        sa.Column("condition_out", sa.String(12), nullable=False, server_default="good"),
        sa.Column("condition_in", sa.String(12), nullable=True),
        sa.Column("document_file_id", sa.String(512), nullable=True),
        sa.Column("accepted_at", sa.DateTime(), nullable=True),
        sa.Column("note", sa.String(500), nullable=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_asset_assignments_asset_id", "asset_assignments", ["asset_id"])
    op.create_index("ix_asset_assignments_user_id", "asset_assignments", ["user_id"])
    op.create_index("ix_asset_assignments_assigned_at", "asset_assignments", ["assigned_at"])
    op.create_index("ix_asset_assignments_returned_at", "asset_assignments", ["returned_at"])
    # Bitta buyumda BITTA ochiq biriktirish (yuqoridagi izohga qarang).
    op.create_index(
        "uq_asset_open_assignment",
        "asset_assignments",
        ["asset_id"],
        unique=True,
        sqlite_where=sa.text("returned_at IS NULL"),
        postgresql_where=sa.text("returned_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_asset_open_assignment", table_name="asset_assignments")
    op.drop_index("ix_asset_assignments_returned_at", table_name="asset_assignments")
    op.drop_index("ix_asset_assignments_assigned_at", table_name="asset_assignments")
    op.drop_index("ix_asset_assignments_user_id", table_name="asset_assignments")
    op.drop_index("ix_asset_assignments_asset_id", table_name="asset_assignments")
    op.drop_table("asset_assignments")
    op.drop_index("ix_assets_kind", table_name="assets")
    op.drop_table("assets")
