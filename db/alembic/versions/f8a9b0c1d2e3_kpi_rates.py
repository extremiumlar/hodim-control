"""kpi_rates — KPI (bonus) stavkasi saytdan sozlanadigan bo'ldi

Ilgari stavkalar `api/services/bonus.py` da KONSTANTA edi:

    PLACEHOLDER_RATE_PER_CONVERSATION = 2000
    PLACEHOLDER_RATE_PER_VISIT = 5000
    PLACEHOLDER_RATE_PER_VIDEO = 0      # ya'ni video KPI'si doim nol

Oqibati: HR stavkani o'zgartira olmasdi (har safar dasturchi + deploy),
stavka tarixiy emasdi va lavozimga qarab farqlanmasdi. Egasining
2026-08-08 talabi: "KPI stavka bo'limini och, keyin belgilanadi
(mobilografga)".

Jadval ikkita mavjud naqshni birlashtiradi: `FinePolicy` dan 3 darajali
qamrov (global -> lavozim -> xodim), `SalaryRate` dan tarixiylik
(`effective_from`, UPDATE qilinmaydi) — o'tgan oy payslip'i buzilmasin.

MA'LUMOT KIRITILMAYDI: jadval BO'SH qoladi. Stavka topilmasa bonus o'sha
ko'rsatkich uchun 0 bo'ladi — ya'ni migratsiyaning o'zi hech kimning
puliga tegmaydi. Qiymatlarni egasi saytdan kiritadi.

Revision ID: f8a9b0c1d2e3
Revises: e7f8a9b0c1d2
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f8a9b0c1d2e3"
down_revision: Union[str, None] = "e7f8a9b0c1d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "kpi_rates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("scope", sa.String(length=20), nullable=False),
        # Polimorfik: scope='position' -> positions.id, 'user' -> users.id,
        # 'global' -> NULL. Shuning uchun FK ATAYLAB qo'yilmadi (FinePolicy
        # bilan bir xil yechim).
        sa.Column("scope_id", sa.Integer(), nullable=True),
        sa.Column("metric", sa.String(length=30), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("changed_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("deleted_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("deleted_reason", sa.String(length=500), nullable=True),
        sa.UniqueConstraint("scope", "scope_id", "metric", "effective_from", name="uq_kpi_rates_grain"),
    )
    op.create_index("ix_kpi_rates_scope", "kpi_rates", ["scope"])
    op.create_index("ix_kpi_rates_metric", "kpi_rates", ["metric"])
    op.create_index("ix_kpi_rates_effective_from", "kpi_rates", ["effective_from"])


def downgrade() -> None:
    op.drop_index("ix_kpi_rates_effective_from", table_name="kpi_rates")
    op.drop_index("ix_kpi_rates_metric", table_name="kpi_rates")
    op.drop_index("ix_kpi_rates_scope", table_name="kpi_rates")
    op.drop_table("kpi_rates")
