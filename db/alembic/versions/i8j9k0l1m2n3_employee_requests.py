"""employee_requests + source_request_id (teskari bog'liqlik)

ARIZALAR_REJASI.md Bosqich 1 — ariza yadrosi.

`Appeal` dan tub farqi: ariza tasdiqlanganda REAL o'zgarish yozadi (ta'til →
`excused_days` qatorlari, avans → `payroll_adjustments`). Shuning uchun
alohida jadval: `appeals` ataylab «hech narsani hisoblamaydi» tamoyiliga
qurilgan, ikkalasini bir joyga qo'shish o'sha tamoyilni buzardi.

TESKARI BOG'LIQLIK (`source_request_id`): yozilgan qatorlar arizaga havola
qiladi — JSON ro'yxat saqlashdan farqi, «bu sababli kun qayerdan paydo
bo'lgan?» degan teskari savolga ham javob beradi va yetim qator qolmaydi.

⚠️ FK MIGRATSIYADA ATAYLAB YO'Q — faqat oddiy `Integer` + indeks.
`f5a6b7c8d9e0_advance.py:38-43` da hujjatlangan tuzoq: `batch_alter_table`
ichida `ForeignKey` qo'shilsa SQLite'da `CircularDependencyError` chiqadi
(jadval qayta quriladi). Modelda `ForeignKey` qoladi — u niyatni hujjatlaydi
va noldan quriladigan bazada (`create_all`) haqiqiy cheklov bo'ladi.
Bu maydonlarga tayanadigan JOIN yo'q, faqat `WHERE source_request_id = ?`.

Revision ID: i8j9k0l1m2n3
Revises: h7i8j9k0l1m2
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "i8j9k0l1m2n3"
down_revision: Union[str, None] = "h7i8j9k0l1m2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SOURCE_TABLES = ("excused_days", "work_schedule_override", "payroll_adjustments")


def upgrade() -> None:
    op.create_table(
        "employee_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        # Qidiriladigan maydonlar — ALOHIDA ustun (JSON'da emas): to'qnashuv
        # tekshiruvi, avans chegarasi va ta'til balansi shular bo'yicha
        # filtrlaydi, JSON ichida esa indeks bo'lmaydi.
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("amount", sa.Numeric(14, 2), nullable=True),
        # Turga xos, qidirilmaydigan qo'shimchalar.
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("file_id", sa.String(length=200), nullable=True),
        sa.Column("file_type", sa.String(length=20), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        # ⭐ Bosqich 4 (tasdiqlash zanjiri) uchun joy — hozircha to'ldirilmaydi.
        sa.Column("manager_id_at_creation", sa.Integer(), nullable=True),
        sa.Column("manager_decided_by", sa.Integer(), nullable=True),
        sa.Column("manager_decided_at", sa.DateTime(), nullable=True),
        sa.Column("manager_note", sa.Text(), nullable=True),
        sa.Column("decided_by", sa.Integer(), nullable=True),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.Column("applied_at", sa.DateTime(), nullable=True),
        # ⭐ Bosqich 5 («ishdagi ta'tilchi»).
        sa.Column("interrupted_at", sa.DateTime(), nullable=True),
        sa.Column("interrupt_decision", sa.String(length=20), nullable=True),
        sa.Column("sla_reminded_at", sa.DateTime(), nullable=True),
        sa.Column("escalated_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_employee_requests_user_id", "employee_requests", ["user_id"])
    op.create_index("ix_employee_requests_kind", "employee_requests", ["kind"])
    op.create_index("ix_employee_requests_status", "employee_requests", ["status"])
    op.create_index("ix_employee_requests_start_date", "employee_requests", ["start_date"])
    op.create_index("ix_employee_requests_created_at", "employee_requests", ["created_at"])

    for table in _SOURCE_TABLES:
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column("source_request_id", sa.Integer(), nullable=True))
        op.create_index(f"ix_{table}_source_request_id", table, ["source_request_id"])


def downgrade() -> None:
    for table in _SOURCE_TABLES:
        op.drop_index(f"ix_{table}_source_request_id", table_name=table)
        with op.batch_alter_table(table) as batch:
            batch.drop_column("source_request_id")

    for idx in ("created_at", "start_date", "status", "kind", "user_id"):
        op.drop_index(f"ix_employee_requests_{idx}", table_name="employee_requests")
    op.drop_table("employee_requests")
