"""S-29: bilim bazasi qamrovi (sales|hr) + murojaatning avto-javobi.

⚠️ `audience` — MAXFIYLIK CHEGARASI. Mavjud yozuvlarning HAMMASI sotuv
bilim bazasidan kelgan, shuning uchun `server_default='sales'` to'g'ri:
eskilar mijozga ko'rinishda qoladi, faqat yangi HR yozuvlari ajraladi.

Revision ID: kb01e1f2a3b4
Revises: hi01d0e1f2a3
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "kb01e1f2a3b4"
down_revision = "hi01d0e1f2a3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("knowledge_entries") as b:
        b.add_column(
            sa.Column("audience", sa.String(8), nullable=False, server_default="sales")
        )
    op.create_index("ix_knowledge_entries_audience", "knowledge_entries", ["audience"])

    with op.batch_alter_table("hr_inquiries") as b:
        b.add_column(
            sa.Column(
                "auto_answered", sa.Boolean(), nullable=False, server_default=sa.false()
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("hr_inquiries") as b:
        b.drop_column("auto_answered")
    op.drop_index("ix_knowledge_entries_audience", table_name="knowledge_entries")
    with op.batch_alter_table("knowledge_entries") as b:
        b.drop_column("audience")
