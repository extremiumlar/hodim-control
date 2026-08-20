"""document_templates — .docx shablonlari (yangi TZ 3.3 / S-14)

Revision ID: y4z5a6b7c8d9
Revises: x3y4z5a6b7c8
Create Date: 2026-08-20

Shablon fayli serverda saqlanmaydi — Telegram `file_id` (kvota 1 GB).
`placeholders` faylning O'ZIDAN o'qiladi, qo'lda kiritilmaydi.
"""
from alembic import op
import sqlalchemy as sa

revision = "y4z5a6b7c8d9"
down_revision = "x3y4z5a6b7c8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "document_templates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("file_id", sa.String(512), nullable=False),
        sa.Column("placeholders", sa.JSON(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("uploaded_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_document_templates_kind", "document_templates", ["kind"])
    op.create_index("ix_document_templates_is_active", "document_templates", ["is_active"])


def downgrade() -> None:
    op.drop_index("ix_document_templates_is_active", table_name="document_templates")
    op.drop_index("ix_document_templates_kind", table_name="document_templates")
    op.drop_table("document_templates")
