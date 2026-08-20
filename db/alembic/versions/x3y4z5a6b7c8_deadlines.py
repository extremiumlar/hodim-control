"""deadlines + deadline_config — muddat eslatmalari (yangi TZ 3.5 / S-12)

Revision ID: x3y4z5a6b7c8
Revises: w2x3y4z5a6b7
Create Date: 2026-08-19

`due_date` ATAYLAB nullable: hisoblanadigan muddatlar (sinov, shartnoma,
hujjat) sanasi manbasidan o'qiladi va bu yerda SAQLANMAYDI — aks holda
manba o'zgarganda nusxa eskirib, tizim ikki xil muddat ko'rsatardi.
"""
from alembic import op
import sqlalchemy as sa

revision = "x3y4z5a6b7c8"
down_revision = "w2x3y4z5a6b7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "deadlines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("responsible_role", sa.String(16), nullable=True),
        sa.Column("source_kind", sa.String(16), nullable=True),
        sa.Column("source_id", sa.Integer(), nullable=True),
        sa.Column("reminded_at", sa.Date(), nullable=True),
        sa.Column("status", sa.String(12), nullable=False, server_default="open"),
        sa.Column("note", sa.String(500), nullable=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_deadlines_user_id", "deadlines", ["user_id"])
    op.create_index("ix_deadlines_kind", "deadlines", ["kind"])
    op.create_index("ix_deadlines_due_date", "deadlines", ["due_date"])
    op.create_index("ix_deadlines_status", "deadlines", ["status"])
    # Hisoblanadigan muddat uchun BITTA iz qatori bo'lsin: cron ikki marta
    # ishlasa ham ikkinchi qator yaratilmasin. Qisman indeks — qo'lda
    # kiritilgan qatorlarda (`source_kind IS NULL`) cheklov yo'q.
    op.create_index(
        "uq_deadlines_source",
        "deadlines",
        ["user_id", "kind", "source_kind", "source_id"],
        unique=True,
        sqlite_where=sa.text("source_kind IS NOT NULL"),
        postgresql_where=sa.text("source_kind IS NOT NULL"),
    )

    op.create_table(
        "deadline_config",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("probation_days", sa.Integer(), nullable=False, server_default="90"),
        sa.Column("remind_days", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("deadline_config")
    op.drop_index("uq_deadlines_source", table_name="deadlines")
    op.drop_index("ix_deadlines_status", table_name="deadlines")
    op.drop_index("ix_deadlines_due_date", table_name="deadlines")
    op.drop_index("ix_deadlines_kind", table_name="deadlines")
    op.drop_index("ix_deadlines_user_id", table_name="deadlines")
    op.drop_table("deadlines")
