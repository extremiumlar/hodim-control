"""Operatorni issiq lid taqsimotidan o'chirib/yoqib qo'yish bayrog'i

Egasining talabi (2026-08-06): sinov akkaunti (Tester) va ta'tildagi
operatorga issiq lid TUSHIB QOLMASLIGI kerak. Bayroq yoqilganlar orasidan
`hot_lead._pick_operator` tanlaydi.

Mavjud xodimlarda default: CRM ID biriktirilganlar (ya'ni allaqachon
operator bo'lganlar) TRUE, qolganlar FALSE — bu bugungi xatti-harakatni
o'zgartirmaydi.

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
"""
from alembic import op
import sqlalchemy as sa

revision = "c2d3e4f5a6b7"
down_revision = "b1c2d3e4f5a6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(
            sa.Column("hot_lead_enabled", sa.Boolean(), nullable=False, server_default=sa.false())
        )
    # Bugungi operatorlar (CRM ID bor) — avvalgidek lid olishda davom etsin.
    op.execute(
        "UPDATE users SET hot_lead_enabled = true WHERE crm_visit_external_id IS NOT NULL"
    )


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_column("hot_lead_enabled")
