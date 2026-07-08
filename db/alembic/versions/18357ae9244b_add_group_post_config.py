"""add group_post_config

Revision ID: 18357ae9244b
Revises: 0394ed6a9187
Create Date: 2026-07-08 09:30:50.871913

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '18357ae9244b'
down_revision: Union[str, None] = '0394ed6a9187'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "group_post_config",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("post_hour", sa.Integer(), nullable=False),
        sa.Column("post_minute", sa.Integer(), nullable=False),
        sa.Column("last_posted_date", sa.Date(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("group_post_config")
