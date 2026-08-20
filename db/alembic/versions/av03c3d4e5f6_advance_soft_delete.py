"""avans yumshoq o'chirish + sabab qoidasi (Avans TZ, A-05)

Revision ID: av03c3d4e5f6
Revises: as01b2c3d4e5
Create Date: 2026-08-20

`payroll_adjustments.deleted_at/deleted_by/deleted_reason` — pul yozuvini
butunlay yo'qotish «bu avans qayerga ketdi?» degan savolga javobsiz
qoldiradi. Qator qoladi, lekin barcha o'qish `deleted_at IS NULL` bilan
filtrlanadi (`SalaryRate` dagi bilan bir xil naqsh).

`fine_policies.advance_reason_required` — avans sababi majburiymi.
DEFAULT `false`: bot oqimida xodim tugma bosib avans so'raydi va matn
yozmaydi; majburiy qilsak o'sha oqim buziladi. HR panelidan yoqadi.
"""
from alembic import op
import sqlalchemy as sa

revision = "av03c3d4e5f6"
down_revision = "as01b2c3d4e5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("payroll_adjustments") as batch:
        batch.add_column(sa.Column("deleted_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("deleted_by", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("deleted_reason", sa.String(500), nullable=True))
    with op.batch_alter_table("fine_policies") as batch:
        batch.add_column(
            sa.Column(
                "advance_reason_required",
                sa.Boolean(),
                nullable=False,
                server_default="0",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("fine_policies") as batch:
        batch.drop_column("advance_reason_required")
    with op.batch_alter_table("payroll_adjustments") as batch:
        batch.drop_column("deleted_reason")
        batch.drop_column("deleted_by")
        batch.drop_column("deleted_at")
