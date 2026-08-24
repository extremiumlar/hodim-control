"""S-45: onboarding — shablon, qadam, reja, progress (yangi TZ 3.2).

⚠️ FK lar MODELDA e'lon qilinadi, bu yerda oddiy `Integer`. Loyiha
naqshi (`og01d6e7f8a9`): SQLite `batch_alter_table` NOMSIZ FK bilan
yiqiladi («Constraint must have a name»).

⚠️ QISMAN UNIQUE INDEKS: bir xodimda bir vaqtda bitta FAOL reja.
Tugagan rejalar tarix bo'lib qoladi va ular uchun cheklov
bo'lmasligi kerak, shuning uchun oddiy UNIQUE emas — `WHERE`
sharti bilan. `__table_args__` da bunday indeksni ifodalab
bo'lmaydi, shuning uchun u faqat MIGRATSIYADA (loyiha naqshi).

Revision ID: ob01f8a9b0c1
Revises: ak01e7f8a9b0
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "ob01f8a9b0c1"
down_revision = "ak01e7f8a9b0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "onboarding_templates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("position_id", sa.Integer(), nullable=True),
        sa.Column("role", sa.String(length=20), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_ob_tpl_position", "onboarding_templates", ["position_id"])
    op.create_index("ix_ob_tpl_role", "onboarding_templates", ["role"])
    op.create_index("ix_ob_tpl_active", "onboarding_templates", ["is_active"])
    op.create_index("ix_ob_tpl_deleted", "onboarding_templates", ["deleted_at"])

    op.create_table(
        "onboarding_steps",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("template_id", sa.Integer(), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("kind", sa.String(length=16), nullable=False, server_default="task"),
        sa.Column("owner_role", sa.String(length=20), nullable=True),
        sa.Column("due_offset_days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ref_id", sa.Integer(), nullable=True),
        sa.Column("ref_text", sa.String(length=60), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_ob_step_tpl", "onboarding_steps", ["template_id"])
    op.create_index("ix_ob_step_kind", "onboarding_steps", ["kind"])
    op.create_index("ix_ob_step_deleted", "onboarding_steps", ["deleted_at"])

    op.create_table(
        "onboarding_plans",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("template_id", sa.Integer(), nullable=True),
        sa.Column("template_name", sa.String(length=200), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=False, server_default="active"),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_ob_plan_user", "onboarding_plans", ["user_id"])
    op.create_index("ix_ob_plan_status", "onboarding_plans", ["status"])
    op.create_index("ix_ob_plan_tpl", "onboarding_plans", ["template_id"])
    op.create_index("ix_ob_plan_start", "onboarding_plans", ["start_date"])
    #  ⚠️ BIR XODIMDA BITTA FAOL REJA — qisman unique indeks.
    op.create_index(
        "uq_ob_plan_active_user",
        "onboarding_plans",
        ["user_id"],
        unique=True,
        sqlite_where=sa.text("status = 'active'"),
        postgresql_where=sa.text("status = 'active'"),
    )

    op.create_table(
        "onboarding_progress",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("plan_id", sa.Integer(), nullable=False),
        sa.Column("step_id", sa.Integer(), nullable=True),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("kind", sa.String(length=16), nullable=False, server_default="task"),
        sa.Column("owner_role", sa.String(length=20), nullable=True),
        sa.Column("owner_user_id", sa.Integer(), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("ref_id", sa.Integer(), nullable=True),
        sa.Column("ref_text", sa.String(length=60), nullable=True),
        sa.Column("done_at", sa.DateTime(), nullable=True),
        sa.Column("done_by", sa.Integer(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
    )
    op.create_index("ix_ob_prog_plan", "onboarding_progress", ["plan_id"])
    op.create_index("ix_ob_prog_due", "onboarding_progress", ["due_date"])
    op.create_index("ix_ob_prog_done", "onboarding_progress", ["done_at"])


def downgrade() -> None:
    op.drop_table("onboarding_progress")
    op.drop_index("uq_ob_plan_active_user", table_name="onboarding_plans")
    op.drop_table("onboarding_plans")
    op.drop_table("onboarding_steps")
    op.drop_table("onboarding_templates")
