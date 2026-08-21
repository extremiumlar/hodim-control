"""employee_documents ro'yxatga olish belgisi (yangi TZ 3.28 / S-27)

Revision ID: cr01c9d0e1f2
Revises: pc01b8c9d0e1
Create Date: 2026-08-21

⚠️ TIZIM RO'YXATGA OLISHNI BAJARMAYDI — bu tashqi jarayon (mehnat
organi). Tizim faqat «qilindimi?» degan BELGINI yuritadi. Aks holda HR
uni bajarilgan deb o'ylab, aslida qilinmagan bo'lardi.

`registered_at` indeksli: «belgisiz shartnomalar» so'rovi kadr auditida
(3.30) ham ishlatiladi.
"""
from alembic import op
import sqlalchemy as sa

revision = "cr01c9d0e1f2"
down_revision = "pc01b8c9d0e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("employee_documents") as batch:
        batch.add_column(sa.Column("registered_at", sa.Date(), nullable=True))
        #  ⚠️ FK ATAYLAB e'lon qilinmaydi. SQLite `batch_alter_table`
        #  jadvalni qayta yaratadi va nomsiz cheklovda «Constraint must
        #  have a name» bilan yiqiladi. Loyihadagi mavjud naqsh shu
        #  (`av02b2c3d4e5_advance_issued.py` dagi `issued_by`): bog'lanish
        #  MODELDA e'lon qilinadi, ORM uni ishlatadi.
        batch.add_column(sa.Column("registered_by", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("registration_note", sa.String(500), nullable=True))
    op.create_index(
        "ix_employee_documents_registered_at", "employee_documents", ["registered_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_employee_documents_registered_at", table_name="employee_documents")
    with op.batch_alter_table("employee_documents") as batch:
        batch.drop_column("registration_note")
        batch.drop_column("registered_by")
        batch.drop_column("registered_at")
