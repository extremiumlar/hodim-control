"""Issiq lid qoidalari: sovish muddati + jarima, bosqichli eslatmalar

Egasining talabi (2026-08-06):
  - HR o'z panelidan har bir SOVUTILGAN issiq lid uchun jarima summasini va
    lid necha daqiqada sovishini belgilaydi (boshlang'ich: 10 daqiqa, 0 so'm);
  - operatorga 3/5/7/9-daqiqada shaxsiy ogohlantirish yuboriladi — qaysi
    bosqich yuborilgani `hot_lead.last_reminder_minute` da saqlanadi;
  - sovutish e'lon qilinganda amaldagi jarima summasi yozuvga NUSXA olinadi
    (`hot_lead.fine_amount`), keyin HR summani o'zgartirsa tarix buzilmasin.

Revision ID: b1c2d3e4f5a6
Revises: a9b0c1d2e3f4
"""
from alembic import op
import sqlalchemy as sa

revision = "b1c2d3e4f5a6"
down_revision = "a9b0c1d2e3f4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # batch_alter_table — SQLite (lokal dev) va PostgreSQL (production) ikkalasida
    # ham ishlashi uchun (loyiha qoidasi).
    with op.batch_alter_table("fine_policies") as batch:
        batch.add_column(sa.Column("hot_lead_cool_minutes", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("hot_lead_fine", sa.Numeric(12, 2), nullable=True))

    with op.batch_alter_table("hot_lead") as batch:
        batch.add_column(
            sa.Column("last_reminder_minute", sa.Integer(), nullable=False, server_default="0")
        )
        batch.add_column(sa.Column("fine_amount", sa.Numeric(12, 2), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("hot_lead") as batch:
        batch.drop_column("fine_amount")
        batch.drop_column("last_reminder_minute")

    with op.batch_alter_table("fine_policies") as batch:
        batch.drop_column("hot_lead_fine")
        batch.drop_column("hot_lead_cool_minutes")
