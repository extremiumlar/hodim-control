"""attendance_digest_config.absent_marked_date — absent yozish qo'riqchisi

Revision ID: d7e8f9a0b1c2
Revises: a1b2c3d4e5f6
Create Date: 2026-07-26 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d7e8f9a0b1c2"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("attendance_digest_config") as batch:
        batch.add_column(sa.Column("absent_marked_date", sa.Date(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("attendance_digest_config") as batch:
        batch.drop_column("absent_marked_date")
