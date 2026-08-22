"""S-33: kurs tayinlash va natija jadvallari (yangi TZ 3.1).

⚠️ `uq_course_assignment_active` — QISMAN unique indeks
(`deleted_at IS NULL`). Aynan u «bir xodimga bir kurs ikki marta
tayinlanmaydi» qoidasini bazada MAJBURLAYDI: kodda qo'riqchi unutilsa
ham dublikat yozilmaydi.

Qisman bo'lishi SHART: to'liq unique bilan yillik qayta o'qitish
(xavfsizlik yo'riqnomasi har yili qayta o'tiladi) umuman mumkin
bo'lmasdi. Eskisini yumshoq o'chirib yangisini tayinlash yo'li ochiq.

Revision ID: cr03a3b4c5d6
Revises: cr02f2a3b4c5
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "cr03a3b4c5d6"
down_revision = "cr02f2a3b4c5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "course_assignments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "course_id",
            sa.Integer(),
            sa.ForeignKey("courses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(12), nullable=False, server_default="assigned"),
        sa.Column("current_material", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("current_q", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("attempt_no", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("answers", sa.JSON(), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        #  ⚠️ FK modelda e'lon qilinadi, bu yerda oddiy `Integer` —
        #  loyiha naqshi (`av02b2c3d4e5_advance_issued`): SQLite
        #  `batch_alter_table` nomsiz FK bilan yiqiladi.
        sa.Column("assigned_by", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_course_assignments_course_id", "course_assignments", ["course_id"]
    )
    op.create_index("ix_course_assignments_user_id", "course_assignments", ["user_id"])
    op.create_index("ix_course_assignments_status", "course_assignments", ["status"])
    op.create_index("ix_course_assignments_due_date", "course_assignments", ["due_date"])
    op.create_index(
        "ix_course_assignments_deleted_at", "course_assignments", ["deleted_at"]
    )
    #  ⚠️ QISMAN UNIQUE — dublikat tayinlashni BAZADA to'sadi.
    op.create_index(
        "uq_course_assignment_active",
        "course_assignments",
        ["user_id", "course_id"],
        unique=True,
        sqlite_where=sa.text("deleted_at IS NULL"),
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    op.create_table(
        "course_results",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "assignment_id",
            sa.Integer(),
            sa.ForeignKey("course_assignments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("attempt_no", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("percent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("passed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "pending_review", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("answers", sa.JSON(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("assignment_id", "attempt_no", name="uq_course_result_attempt"),
    )
    op.create_index("ix_course_results_assignment_id", "course_results", ["assignment_id"])
    op.create_index("ix_course_results_passed", "course_results", ["passed"])
    op.create_index("ix_course_results_pending_review", "course_results", ["pending_review"])


def downgrade() -> None:
    op.drop_table("course_results")
    op.drop_index("uq_course_assignment_active", table_name="course_assignments")
    op.drop_table("course_assignments")
