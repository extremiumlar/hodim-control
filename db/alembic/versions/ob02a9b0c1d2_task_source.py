"""S-46: vazifa manbai — onboarding vazifalarini ajratish (yangi TZ 3.2).

`tasks.source` = "onboarding" bo'lgan yozuvlar VAZIFA STATISTIKASIGA
KIRMAYDI. Sabab: yangi xodimga birinchi kunlarida 10-15 qadam
tushadi va ular oddiy vazifa deb sanalsa, «bajarilgan vazifalar
foizi» sun'iy ravishda o'zgarardi.

`NULL` — odatdagi ish topshirig'i (mavjud yozuvlarning HAMMASI shu
holatda qoladi, ya'ni eski statistika o'zgarmaydi).

Revision ID: ob02a9b0c1d2
Revises: ob01f8a9b0c1
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "ob02a9b0c1d2"
down_revision = "ob01f8a9b0c1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("tasks") as b:
        b.add_column(sa.Column("source", sa.String(length=20), nullable=True))
        b.add_column(sa.Column("source_id", sa.Integer(), nullable=True))
    op.create_index("ix_tasks_source", "tasks", ["source"])
    op.create_index("ix_tasks_source_id", "tasks", ["source_id"])


def downgrade() -> None:
    op.drop_index("ix_tasks_source_id", table_name="tasks")
    op.drop_index("ix_tasks_source", table_name="tasks")
    with op.batch_alter_table("tasks") as b:
        b.drop_column("source_id")
        b.drop_column("source")
