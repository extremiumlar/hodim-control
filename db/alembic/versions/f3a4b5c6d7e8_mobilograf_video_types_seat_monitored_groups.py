"""mobilograf: video turlari (oddiy/dumaloq), xodim "o'rin" (seat), kuzatuv guruhlari

Revision ID: f3a4b5c6d7e8
Revises: e2f3a4b5c6d7
Create Date: 2026-07-22 12:00:00.000000

"""
import os
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f3a4b5c6d7e8"
down_revision: Union[str, None] = "e2f3a4b5c6d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("mobilograf_videos") as batch_op:
        # Eski qatorlar "oddiy" deb belgilanadi — dumaloq ilgari alohida kuzatilmagan.
        batch_op.add_column(sa.Column("video_type", sa.String(length=20), nullable=False, server_default="oddiy"))

    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("is_seat", sa.Boolean(), nullable=False, server_default=sa.false()))

    op.create_table(
        "monitored_groups",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("purpose", sa.String(length=30), nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("added_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("purpose", "chat_id", name="uq_monitored_group_purpose_chat"),
    )
    op.create_index("ix_monitored_groups_purpose", "monitored_groups", ["purpose"])

    bind = op.get_bind()

    # --- data: positions.metrics dagi "video"ni "oddiy_video"+"dumaloq_video"ga bo'lish ---
    positions = sa.table("positions", sa.column("id", sa.Integer()), sa.column("metrics", sa.JSON()))
    for row in bind.execute(sa.select(positions.c.id, positions.c.metrics)).fetchall():
        metrics = row.metrics
        if metrics and "video" in metrics:
            new_metrics = [m for m in metrics if m != "video"] + ["oddiy_video", "dumaloq_video"]
            bind.execute(positions.update().where(positions.c.id == row.id).values(metrics=new_metrics))

    # --- data: monitored_groups'ni eski .env qiymatlaridan bir martalik seed qilish
    # (deploy qilingandan keyin xatti-harakat o'zgarmasin — dasturchi keyin botdan
    # xohlagancha o'zgartira oladi) ---
    seed_rows: list[dict] = []
    main_chat_raw = (os.getenv("TELEGRAM_GROUP_CHAT_ID") or "").strip()
    if main_chat_raw and main_chat_raw != "0":
        try:
            main_chat_id = int(main_chat_raw)
        except ValueError:
            main_chat_id = 0
        if main_chat_id:
            seed_rows.append({"purpose": "main", "chat_id": main_chat_id, "title": None})
            seed_rows.append({"purpose": "mobilograf", "chat_id": main_chat_id, "title": None})

    for part in (os.getenv("TELEGRAM_STATS_GROUP_CHAT_ID") or "").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            stats_chat_id = int(part)
        except ValueError:
            continue
        if stats_chat_id:
            seed_rows.append({"purpose": "stats", "chat_id": stats_chat_id, "title": None})

    if seed_rows:
        monitored_groups = sa.table(
            "monitored_groups",
            sa.column("purpose", sa.String()),
            sa.column("chat_id", sa.BigInteger()),
            sa.column("title", sa.String()),
        )
        bind.execute(monitored_groups.insert(), seed_rows)


def downgrade() -> None:
    op.drop_index("ix_monitored_groups_purpose", table_name="monitored_groups")
    op.drop_table("monitored_groups")

    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("is_seat")

    with op.batch_alter_table("mobilograf_videos") as batch_op:
        batch_op.drop_column("video_type")

    bind = op.get_bind()
    positions = sa.table("positions", sa.column("id", sa.Integer()), sa.column("metrics", sa.JSON()))
    for row in bind.execute(sa.select(positions.c.id, positions.c.metrics)).fetchall():
        metrics = row.metrics
        if metrics and "oddiy_video" in metrics:
            new_metrics = [m for m in metrics if m not in ("oddiy_video", "dumaloq_video")] + ["video"]
            bind.execute(positions.update().where(positions.c.id == row.id).values(metrics=new_metrics))
