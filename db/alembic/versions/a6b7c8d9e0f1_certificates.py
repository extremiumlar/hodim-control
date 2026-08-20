"""certificates — berilgan ma'lumotnomalar arxivi (yangi TZ 3.9 / S-17)

Revision ID: a6b7c8d9e0f1
Revises: z5a6b7c8d9e0
Create Date: 2026-08-20

`number` UNIKAL: ma'lumotnoma raqami rasmiy rekvizit, ikkita hujjat bir
xil raqam bilan chiqsa tashqi tashkilot ularni qalbaki deb hisoblaydi.
Unikallik BAZA darajasida — kod darajasidagi hisoblash parallel tasdiqda
yetarli emas.
"""
from alembic import op
import sqlalchemy as sa

revision = "a6b7c8d9e0f1"
down_revision = "z5a6b7c8d9e0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "certificates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("request_id", sa.Integer(), sa.ForeignKey("employee_requests.id"), nullable=True),
        sa.Column("purpose", sa.String(16), nullable=False),
        sa.Column("number", sa.String(32), nullable=False, unique=True),
        sa.Column("include_salary", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("avg_salary", sa.Numeric(14, 2), nullable=True),
        sa.Column("template_id", sa.Integer(), sa.ForeignKey("document_templates.id"), nullable=True),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("employee_documents.id"), nullable=True),
        sa.Column("issued_at", sa.Date(), nullable=False),
        sa.Column("issued_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_certificates_user_id", "certificates", ["user_id"])
    op.create_index("ix_certificates_request_id", "certificates", ["request_id"])
    op.create_index("ix_certificates_purpose", "certificates", ["purpose"])
    op.create_index("ix_certificates_issued_at", "certificates", ["issued_at"])
    op.create_index("uq_certificates_number", "certificates", ["number"], unique=True)


def downgrade() -> None:
    op.drop_index("uq_certificates_number", table_name="certificates")
    op.drop_index("ix_certificates_issued_at", table_name="certificates")
    op.drop_index("ix_certificates_purpose", table_name="certificates")
    op.drop_index("ix_certificates_request_id", table_name="certificates")
    op.drop_index("ix_certificates_user_id", table_name="certificates")
    op.drop_table("certificates")
