"""Oylik ish haqi + kechikish jarimasi + qo'shimcha ish jadvallari (Bosqich 1)

8 ta yangi jadval: salary_rates, overtime_profiles, fine_policies,
overtime_entries, payroll_periods, payslips, payslip_items,
payroll_adjustments. Batafsil — OYLIK_JARIMA_REJASI.md 2-bo'lim.

Hammasi bo'sh/o'chiq holatda yaratiladi — mavjud tizim xatti-harakati
o'zgarmaydi (`fine_policies`da hech qanday qator yo'q, `overtime_profiles`da
`enabled=False`).

Revision ID: 88b50e2fbcb1
Revises: f9e8d7c6b5a4
Create Date: 2026-07-27
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "88b50e2fbcb1"
down_revision: Union[str, None] = "f9e8d7c6b5a4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "salary_rates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("pay_basis", sa.String(20), nullable=False, server_default="monthly"),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("changed_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "effective_from", name="uq_salary_rates_user_date"),
    )
    op.create_index("ix_salary_rates_user_id", "salary_rates", ["user_id"])
    op.create_index("ix_salary_rates_effective_from", "salary_rates", ["effective_from"])

    op.create_table(
        "overtime_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("mode", sa.String(20), nullable=False, server_default="derived"),
        sa.Column("fixed_rate_per_hour", sa.Numeric(12, 2), nullable=True),
        sa.Column("multiplier", sa.Numeric(3, 2), nullable=True),
        sa.Column("norm_hours_source", sa.String(20), nullable=False, server_default="schedule"),
        sa.Column("fixed_norm_hours_per_month", sa.Integer(), nullable=True),
        sa.Column("min_minutes", sa.Integer(), nullable=False, server_default="15"),
        sa.Column("daily_cap_minutes", sa.Integer(), nullable=True),
        sa.Column("monthly_cap_minutes", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", name="uq_overtime_profiles_user"),
    )
    op.create_index("ix_overtime_profiles_user_id", "overtime_profiles", ["user_id"])

    op.create_table(
        "fine_policies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("scope", sa.String(20), nullable=False),
        sa.Column("scope_id", sa.Integer(), nullable=True),
        sa.Column("grace_minutes", sa.Integer(), nullable=True),
        sa.Column("free_late_days_per_month", sa.Integer(), nullable=True),
        sa.Column("free_late_minutes_per_month", sa.Integer(), nullable=True),
        sa.Column("fine_mode", sa.String(20), nullable=False, server_default="per_day"),
        sa.Column("fine_per_day", sa.Numeric(12, 2), nullable=True),
        sa.Column("fine_per_minute", sa.Numeric(12, 2), nullable=True),
        sa.Column("tiers", sa.JSON(), nullable=True),
        sa.Column("percent_of_daily", sa.Numeric(5, 2), nullable=True),
        sa.Column("absent_mode", sa.String(20), nullable=False, server_default="fixed"),
        sa.Column("absent_fine", sa.Numeric(12, 2), nullable=True),
        sa.Column("early_leave_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("early_leave_per_minute", sa.Numeric(12, 2), nullable=True),
        sa.Column("monthly_cap_percent", sa.Numeric(5, 2), nullable=True),
        sa.Column("monthly_cap_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("fine_applies_to", sa.String(20), nullable=False, server_default="net_salary"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("scope", "scope_id", name="uq_fine_policies_scope"),
    )

    op.create_table(
        "overtime_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("minutes", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(20), nullable=False, server_default="manual"),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("note", sa.String(500), nullable=True),
        sa.Column("decided_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "date", name="uq_overtime_entries_user_date"),
    )
    op.create_index("ix_overtime_entries_user_id", "overtime_entries", ["user_id"])
    op.create_index("ix_overtime_entries_date", "overtime_entries", ["date"])
    op.create_index("ix_overtime_entries_status", "overtime_entries", ["status"])

    op.create_table(
        "payroll_periods",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("period", sa.String(7), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("calculated_at", sa.DateTime(), nullable=True),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("locked", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("note", sa.String(500), nullable=True),
        sa.UniqueConstraint("period", name="uq_payroll_periods_period"),
    )
    op.create_index("ix_payroll_periods_period", "payroll_periods", ["period"])

    op.create_table(
        "payslips",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("period", sa.String(7), nullable=False),
        sa.Column("base_amount", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("pay_basis", sa.String(20), nullable=False, server_default="monthly"),
        sa.Column("rate_snapshot", sa.Numeric(12, 2), nullable=True),
        sa.Column("scheduled_days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("worked_days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("absent_days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("excused_days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("scheduled_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("worked_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("late_days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("late_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("fined_late_days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("fined_late_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("fine_amount", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("absent_deduction", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("overtime_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("overtime_amount", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("overtime_rate_snapshot", sa.Numeric(12, 2), nullable=True),
        sa.Column("bonus_amount", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("adjustments_plus", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("adjustments_minus", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("gross", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("net", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(3), nullable=False, server_default="UZS"),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("breakdown", sa.JSON(), nullable=True),
        sa.Column("calculated_at", sa.DateTime(), nullable=True),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("user_id", "period", name="uq_payslips_user_period"),
    )
    op.create_index("ix_payslips_user_id", "payslips", ["user_id"])
    op.create_index("ix_payslips_period", "payslips", ["period"])
    op.create_index("ix_payslips_status", "payslips", ["status"])

    op.create_table(
        "payslip_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("payslip_id", sa.Integer(), sa.ForeignKey("payslips.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("label", sa.String(255), nullable=False),
        sa.Column("quantity", sa.Numeric(10, 2), nullable=True),
        sa.Column("rate", sa.Numeric(12, 2), nullable=True),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_payslip_items_payslip_id", "payslip_items", ["payslip_id"])

    op.create_table(
        "payroll_adjustments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("period", sa.String(7), nullable=False),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_payroll_adjustments_user_id", "payroll_adjustments", ["user_id"])
    op.create_index("ix_payroll_adjustments_period", "payroll_adjustments", ["period"])


def downgrade() -> None:
    op.drop_index("ix_payroll_adjustments_period", table_name="payroll_adjustments")
    op.drop_index("ix_payroll_adjustments_user_id", table_name="payroll_adjustments")
    op.drop_table("payroll_adjustments")

    op.drop_index("ix_payslip_items_payslip_id", table_name="payslip_items")
    op.drop_table("payslip_items")

    op.drop_index("ix_payslips_status", table_name="payslips")
    op.drop_index("ix_payslips_period", table_name="payslips")
    op.drop_index("ix_payslips_user_id", table_name="payslips")
    op.drop_table("payslips")

    op.drop_index("ix_payroll_periods_period", table_name="payroll_periods")
    op.drop_table("payroll_periods")

    op.drop_index("ix_overtime_entries_status", table_name="overtime_entries")
    op.drop_index("ix_overtime_entries_date", table_name="overtime_entries")
    op.drop_index("ix_overtime_entries_user_id", table_name="overtime_entries")
    op.drop_table("overtime_entries")

    op.drop_table("fine_policies")

    op.drop_index("ix_overtime_profiles_user_id", table_name="overtime_profiles")
    op.drop_table("overtime_profiles")

    op.drop_index("ix_salary_rates_effective_from", table_name="salary_rates")
    op.drop_index("ix_salary_rates_user_id", table_name="salary_rates")
    op.drop_table("salary_rates")
