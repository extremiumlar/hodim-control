"""profile_change_requests + users shaxsiy maydonlari (TZ 3.26 / S-26)

Revision ID: pc01b8c9d0e1
Revises: sr01a7b8c9d0
Create Date: 2026-08-21

Xodim shaxsiy ma'lumotini TO'G'RIDAN-TO'G'RI o'zgartira olmaydi: so'rov
yuboradi, HR tasdiqlaydi, shundan keyin `users` ga yoziladi.

`old_value` so'rov YUBORILGAN paytdagi qiymatni saqlaydi — tasdiqlashda
qaytadan o'qilmaydi, chunki HR aynan nimani ko'rib tasdiqlagani qolishi
kerak.
"""
from alembic import op
import sqlalchemy as sa

revision = "pc01b8c9d0e1"
down_revision = "sr01a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("phone", sa.String(32), nullable=True))
        batch.add_column(sa.Column("address", sa.String(300), nullable=True))
        batch.add_column(sa.Column("marital_status", sa.String(32), nullable=True))
        batch.add_column(sa.Column("emergency_contact", sa.String(200), nullable=True))

    op.create_table(
        "profile_change_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("field", sa.String(24), nullable=False),
        sa.Column("old_value", sa.String(300), nullable=True),
        sa.Column("new_value", sa.String(300), nullable=False),
        sa.Column("status", sa.String(12), nullable=False, server_default="pending"),
        sa.Column("decided_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
        sa.Column("decision_note", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_profile_change_requests_user_id", "profile_change_requests", ["user_id"])
    op.create_index("ix_profile_change_requests_field", "profile_change_requests", ["field"])
    op.create_index("ix_profile_change_requests_status", "profile_change_requests", ["status"])
    op.create_index(
        "ix_profile_change_requests_created_at", "profile_change_requests", ["created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_profile_change_requests_created_at", table_name="profile_change_requests")
    op.drop_index("ix_profile_change_requests_status", table_name="profile_change_requests")
    op.drop_index("ix_profile_change_requests_field", table_name="profile_change_requests")
    op.drop_index("ix_profile_change_requests_user_id", table_name="profile_change_requests")
    op.drop_table("profile_change_requests")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("emergency_contact")
        batch.drop_column("marital_status")
        batch.drop_column("address")
        batch.drop_column("phone")
