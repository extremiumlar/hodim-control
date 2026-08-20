"""announcements + announcement_config — ichki e'lonlar (yangi TZ 3.12 / S-21)

Revision ID: an01d4e5f6a7
Revises: mg02a1b2c3d4
Create Date: 2026-08-20

Qamrov (`audience` + `scope_ids`) — ko'rinishni bezash emas, FILTR:
qamrovga kirmagan xodimga e'lon UMUMAN ko'rinmaydi (TZ qabul mezoni).

`daily_limit` — cheklovsiz tizim e'lon spamiga aylanadi va muhim e'lon
ham o'qilmay qoladi.
"""
from alembic import op
import sqlalchemy as sa

revision = "an01d4e5f6a7"
down_revision = "mg02a1b2c3d4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "announcements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("audience", sa.String(12), nullable=False, server_default="all"),
        sa.Column("scope_ids", sa.JSON(), nullable=True),
        sa.Column("important", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("file_id", sa.String(512), nullable=True),
        sa.Column("file_type", sa.String(16), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("author_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_announcements_important", "announcements", ["important"])
    # Kunlik limit tekshiruvi va ro'yxat shu indeksdan foydalanadi.
    op.create_index("ix_announcements_created_at", "announcements", ["created_at"])

    op.create_table(
        "announcement_config",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("daily_limit", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("announcement_config")
    op.drop_index("ix_announcements_created_at", table_name="announcements")
    op.drop_index("ix_announcements_important", table_name="announcements")
    op.drop_table("announcements")
