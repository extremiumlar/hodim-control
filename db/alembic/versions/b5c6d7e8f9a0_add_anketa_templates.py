"""Yuklanadigan anketa savol to'plamlari (Word/.txt)

Dasturchi botga .docx tashlaydi → savollar ajratilib anketa_templates'ga
yoziladi; sessiyada har xodimga o'z to'plami biriktiriladi
(anketa_assignments.template_id). Ichki 5 to'plam (toplam 1-5) o'z kuchida
qoladi — template_id NULL bo'lganda ishlatiladi.

Faqat CREATE TABLE + ADD COLUMN (jadval qayta qurilmaydi — mavjud javoblar
xavfsiz).

Revision ID: b5c6d7e8f9a0
Revises: a4b5c6d7e8f9
Create Date: 2026-07-20
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b5c6d7e8f9a0"
down_revision: Union[str, None] = "a4b5c6d7e8f9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "anketa_templates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("questions", sa.JSON(), nullable=False),
        sa.Column("question_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_anketa_templates_is_active", "anketa_templates", ["is_active"])
    # DIQQAT: ustun FK cheklovisiz qo'shiladi — SQLite ALTER TABLE bilan
    # constraint qo'sha olmaydi, batch rejim esa jadvalni qayta quradi
    # (anketa_answers CASCADE bilan bog'langan — mavjud javoblar xavf ostida
    # qolmasin). Model darajasidagi ForeignKey ORM uchun yetarli.
    op.add_column("anketa_assignments", sa.Column("template_id", sa.Integer(), nullable=True))
    op.create_index(
        "ix_anketa_assignments_template_id", "anketa_assignments", ["template_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_anketa_assignments_template_id", table_name="anketa_assignments")
    op.drop_column("anketa_assignments", "template_id")
    op.drop_index("ix_anketa_templates_is_active", table_name="anketa_templates")
    op.drop_table("anketa_templates")
