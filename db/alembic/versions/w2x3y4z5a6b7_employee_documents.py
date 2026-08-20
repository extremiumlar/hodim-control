"""employee_documents — kadr hujjatlari arxivi (yangi TZ 3.4 / S-10)

Revision ID: w2x3y4z5a6b7
Revises: v1w2x3y4z5a6
Create Date: 2026-08-19

Fayl serverda saqlanmaydi — faqat Telegram `file_id` (disk kvotasi 1 GB).
O'chirish yumshoq: kadr hujjatini butunlay yo'qotish huquqiy xavf.
"""
from alembic import op
import sqlalchemy as sa

revision = "w2x3y4z5a6b7"
down_revision = "v1w2x3y4z5a6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "employee_documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("doc_type", sa.String(24), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("file_id", sa.String(512), nullable=False),
        sa.Column("file_type", sa.String(16), nullable=False, server_default="document"),
        sa.Column("uploaded_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("issued_at", sa.Date(), nullable=True),
        sa.Column("expires_at", sa.Date(), nullable=True),
        sa.Column("note", sa.String(500), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_employee_documents_user_id", "employee_documents", ["user_id"])
    op.create_index("ix_employee_documents_doc_type", "employee_documents", ["doc_type"])
    # S-12 muddat eslatmalari «yaqinda tugaydiganlar» ni shu indeks bilan topadi.
    op.create_index("ix_employee_documents_expires_at", "employee_documents", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_employee_documents_expires_at", table_name="employee_documents")
    op.drop_index("ix_employee_documents_doc_type", table_name="employee_documents")
    op.drop_index("ix_employee_documents_user_id", table_name="employee_documents")
    op.drop_table("employee_documents")
