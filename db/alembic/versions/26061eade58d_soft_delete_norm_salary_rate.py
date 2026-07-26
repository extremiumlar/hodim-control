"""Yumshoq o'chirish: norms + salary_rates (Bosqich 3.5 — Dasturchi rejimi)

Xato kiritilgan tarixiy yozuvni (norma yoki oylik stavka) butunlay
yo'qotmasdan "faol emas" qilish uchun. Barcha o'qish so'rovlari
(`_current_value`, `resolve_rate`, `_first_rate`) `deleted_at IS NULL`
bilan filtrlanadi (kod tomonda alohida tekshirilgan).

Revision ID: 26061eade58d
Revises: 88b50e2fbcb1
Create Date: 2026-07-27
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "26061eade58d"
down_revision: Union[str, None] = "88b50e2fbcb1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # SQLite batch-alter (jadvalni qayta yaratish orqali) qo'shilayotgan FK
    # cheklovi uchun NOM talab qiladi — inline `sa.ForeignKey(...)`dagi
    # sukut nomsiz konstruksiya "Constraint must have a name" xatosini beradi.
    with op.batch_alter_table("norms") as batch:
        batch.add_column(sa.Column("deleted_at", sa.DateTime(), nullable=True))
        batch.add_column(
            sa.Column("deleted_by", sa.Integer(), sa.ForeignKey("users.id", name="fk_norms_deleted_by_users"), nullable=True)
        )
        batch.add_column(sa.Column("deleted_reason", sa.String(500), nullable=True))

    with op.batch_alter_table("salary_rates") as batch:
        batch.add_column(sa.Column("deleted_at", sa.DateTime(), nullable=True))
        batch.add_column(
            sa.Column(
                "deleted_by", sa.Integer(),
                sa.ForeignKey("users.id", name="fk_salary_rates_deleted_by_users"), nullable=True,
            )
        )
        batch.add_column(sa.Column("deleted_reason", sa.String(500), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("salary_rates") as batch:
        batch.drop_column("deleted_reason")
        batch.drop_column("deleted_by")
        batch.drop_column("deleted_at")

    with op.batch_alter_table("norms") as batch:
        batch.drop_column("deleted_reason")
        batch.drop_column("deleted_by")
        batch.drop_column("deleted_at")
