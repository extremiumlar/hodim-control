"""users.birth_date + celebration_posts odam hodisalari (yangi TZ 3.14 / S-22)

Revision ID: bd01e5f6a7b8
Revises: mg03b2c3d4e5
Create Date: 2026-08-20

⚠️ YANGI JADVAL YARATILMAYDI (TZ qabul mezoni). Tug'ilgan kun va ish
yubileyi MAVJUD `celebration` mexanizmidan foydalanadi — faqat uni odam
hodisalarini ham qabul qiladigan qilib kengaytiramiz:

  • `lead_event_id` / `crm_lead_id` nullable bo'ladi (odam hodisasida
    CRM voqeasi yo'q);
  • `dedupe_key` qo'shiladi (`birthday:7:2026`) — takrorlanish
    qo'riqchisi, chunki eski qo'riqchi `lead_event_id` ga tayangan edi.

SQLite ustun turini o'zgartira olmaydi, shuning uchun `batch_alter_table`.
"""
from alembic import op
import sqlalchemy as sa

revision = "bd01e5f6a7b8"
down_revision = "mg03b2c3d4e5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("birth_date", sa.Date(), nullable=True))

    with op.batch_alter_table("celebration_posts") as batch:
        batch.add_column(sa.Column("dedupe_key", sa.String(64), nullable=True))
        batch.alter_column("lead_event_id", existing_type=sa.Integer(), nullable=True)
        batch.alter_column("crm_lead_id", existing_type=sa.Integer(), nullable=True)
    op.create_index(
        "uq_celebration_posts_dedupe_key",
        "celebration_posts",
        ["dedupe_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_celebration_posts_dedupe_key", table_name="celebration_posts")
    with op.batch_alter_table("celebration_posts") as batch:
        batch.drop_column("dedupe_key")
        batch.alter_column("crm_lead_id", existing_type=sa.Integer(), nullable=False)
        batch.alter_column("lead_event_id", existing_type=sa.Integer(), nullable=False)
    with op.batch_alter_table("users") as batch:
        batch.drop_column("birth_date")
