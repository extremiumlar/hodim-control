"""S-34: kursda «majburiy» bayrog'i (yangi TZ 3.1).

Majburiy kurs o'tilmasa muddat eslatmasi (TZ 3.5) yuboriladi va HR
tahlilida «majburiy kurs tugatish %» (TZ 3.31) shundan hisoblanadi.
Mavjud kurslar `false` bo'lib qoladi — ixtiyoriy deb hisoblanadi va
hech kimga kutilmagan eslatma ketmaydi.

Revision ID: cr04b4c5d6e7
Revises: cr03a3b4c5d6
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "cr04b4c5d6e7"
down_revision = "cr03a3b4c5d6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("courses") as b:
        b.add_column(
            sa.Column(
                "is_mandatory", sa.Boolean(), nullable=False, server_default=sa.false()
            )
        )
    op.create_index("ix_courses_is_mandatory", "courses", ["is_mandatory"])


def downgrade() -> None:
    op.drop_index("ix_courses_is_mandatory", table_name="courses")
    with op.batch_alter_table("courses") as b:
        b.drop_column("is_mandatory")
