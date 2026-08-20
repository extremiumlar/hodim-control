"""advance_settings — uch darajali avans sozlamalari (Avans TZ, B-01)

Revision ID: av05e5f6a7b8
Revises: av04d4e5f6a7
Create Date: 2026-08-20

A blokda ikkita sozlama vaqtincha `fine_policies` ga qo'yilgan edi — u
o'sha paytda yagona mavjud «HR paneli sozlamalari» jadvali edi. Avansning
o'z qiymatlari beshta va ular jarima qoidasiga aloqasi yo'q, shuning
uchun alohida jadval.

KO'CHIRISH: `fine_policies` dagi `advance_reason_required` va
`advance_pending_on_close` qiymatlari AYNAN o'sha qamrov bilan
(`scope`/`scope_id`) `advance_settings` ga ko'chiriladi — HR A blokda
kiritgan sozlama yo'qolib ketmasin. Keyin eski ustunlar o'chiriladi.

⚠️ SQLite'da `INSERT ... SELECT` ishlaydi, Postgres'da ham — shuning
uchun oddiy SQL bilan yozilgan (ORM'siz: migratsiya modelning kelajakdagi
holatiga bog'lanib qolmasin).
"""
from alembic import op
import sqlalchemy as sa

revision = "av05e5f6a7b8"
down_revision = "av04d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "advance_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("scope", sa.String(20), nullable=False),
        sa.Column("scope_id", sa.Integer(), nullable=True),
        sa.Column("advance_day", sa.Integer(), nullable=False, server_default="20"),
        sa.Column("coefficient", sa.Numeric(4, 2), nullable=False, server_default="0.5"),
        sa.Column("cap_percent", sa.Numeric(5, 2), nullable=False, server_default="50"),
        sa.Column("min_amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("reminder_time", sa.String(5), nullable=False, server_default="14:00"),
        sa.Column("pending_on_close", sa.String(10), nullable=False, server_default="carry"),
        sa.Column("reason_required", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("effective_from", sa.Date(), nullable=True),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("scope", "scope_id", name="uq_advance_settings_scope"),
    )

    # A blokdagi sozlamalarni ko'chiramiz (yo'qolib ketmasin).
    op.execute(
        "INSERT INTO advance_settings "
        "(scope, scope_id, reason_required, pending_on_close, is_active, updated_at) "
        "SELECT scope, scope_id, advance_reason_required, "
        "       advance_pending_on_close, is_active, CURRENT_TIMESTAMP "
        "FROM fine_policies"
    )

    with op.batch_alter_table("fine_policies") as batch:
        batch.drop_column("advance_pending_on_close")
        batch.drop_column("advance_reason_required")


def downgrade() -> None:
    with op.batch_alter_table("fine_policies") as batch:
        batch.add_column(
            sa.Column(
                "advance_reason_required", sa.Boolean(), nullable=False, server_default="0"
            )
        )
        batch.add_column(
            sa.Column(
                "advance_pending_on_close", sa.String(10), nullable=False, server_default="carry"
            )
        )
    op.drop_table("advance_settings")
