"""push bildirishnomalar: push_tokens + push_settings

Revision ID: f7a8b9c0d1e2
Revises: c1d2e3f4a5b6
Create Date: 2026-07-31

Mobil ilova uchun push infratuzilmasi (MOBIL_ILOVA_REJASI.md 4.3).
`push_settings`da FAQAT standartdan farq qiluvchi tanlov saqlanadi —
shuning uchun jadval odatda deyarli bo'sh turadi.
"""

from alembic import op
import sqlalchemy as sa

revision = "f7a8b9c0d1e2"
down_revision = "c1d2e3f4a5b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "push_tokens",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token", sa.String(length=255), nullable=False),
        sa.Column("platform", sa.String(length=10), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_push_tokens_user_id", "push_tokens", ["user_id"])
    op.create_index("ix_push_tokens_token", "push_tokens", ["token"], unique=True)

    op.create_table(
        "push_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(length=40), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "category", name="uq_push_setting_user_category"),
    )
    op.create_index("ix_push_settings_user_id", "push_settings", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_push_settings_user_id", table_name="push_settings")
    op.drop_table("push_settings")
    op.drop_index("ix_push_tokens_token", table_name="push_tokens")
    op.drop_index("ix_push_tokens_user_id", table_name="push_tokens")
    op.drop_table("push_tokens")
