"""celebration_media + celebration_posts + celebration_claps

Tashrif va shartnoma bo'lganda umumiy guruhga tabrik videosi (yoki GIF) +
«👏 Tabriklash» tugmasi. Videoni Dasturchi/HR/Boshliq botdan almashtiradi.

Video FAYLI serverda saqlanmaydi — Telegram'ning `file_id` si saqlanadi
(`api/telegram_notify.send_file_id` bilan bir xil naqsh).

`celebration_posts.lead_event_id` UNIQUE — takroriy e'lonning yagona ishonchli
to'sig'i: voqealarni ikki manba (webhook + diff-skaner) yozadi, e'lon qiluvchi
esa har daqiqada ishlaydi.

⚠️ FK'lar `celebration_claps.post_id` dan tashqari ATAYLAB oddiy Integer —
`f5a6b7c8d9e0_advance.py` da hujjatlangan tuzoq (SQLite batch_alter_table +
ForeignKey → CircularDependencyError). Bu yerda jadvallar YANGI yaratilyapti,
shuning uchun `create_table` ichidagi FK xavfsiz.

Revision ID: j9k0l1m2n3o4
Revises: i8j9k0l1m2n3
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "j9k0l1m2n3o4"
down_revision: Union[str, None] = "i8j9k0l1m2n3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "celebration_media",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("file_id", sa.String(length=512), nullable=False),
        sa.Column("file_type", sa.String(length=16), nullable=False, server_default="video"),
        sa.Column("caption", sa.String(length=512), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("uploaded_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_celebration_media_kind", "celebration_media", ["kind"])

    op.create_table(
        "celebration_posts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("lead_event_id", sa.Integer(), nullable=False),
        sa.Column("crm_lead_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("chat_id", sa.BigInteger(), nullable=True),
        sa.Column("message_id", sa.BigInteger(), nullable=True),
        sa.Column("claps", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_celebration_posts_kind", "celebration_posts", ["kind"])
    op.create_index(
        "ix_celebration_posts_lead_event_id", "celebration_posts", ["lead_event_id"], unique=True
    )
    op.create_index("ix_celebration_posts_crm_lead_id", "celebration_posts", ["crm_lead_id"])
    op.create_index("ix_celebration_posts_created_at", "celebration_posts", ["created_at"])

    op.create_table(
        "celebration_claps",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "post_id",
            sa.Integer(),
            sa.ForeignKey("celebration_posts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("post_id", "telegram_id", name="uq_celebration_clap"),
    )
    op.create_index("ix_celebration_claps_post_id", "celebration_claps", ["post_id"])


def downgrade() -> None:
    op.drop_index("ix_celebration_claps_post_id", table_name="celebration_claps")
    op.drop_table("celebration_claps")
    op.drop_index("ix_celebration_posts_created_at", table_name="celebration_posts")
    op.drop_index("ix_celebration_posts_crm_lead_id", table_name="celebration_posts")
    op.drop_index("ix_celebration_posts_lead_event_id", table_name="celebration_posts")
    op.drop_index("ix_celebration_posts_kind", table_name="celebration_posts")
    op.drop_table("celebration_posts")
    op.drop_index("ix_celebration_media_kind", table_name="celebration_media")
    op.drop_table("celebration_media")
