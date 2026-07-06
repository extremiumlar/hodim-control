"""add operator_calls_daily

Revision ID: c72ca71126ba
Revises: 63cce1110edc
Create Date: 2026-07-06 21:08:16.111013

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c72ca71126ba'
down_revision: Union[str, None] = '63cce1110edc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "operator_calls_daily",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("responsible_id", sa.Integer(), nullable=False),
        sa.Column("responsible_name", sa.String(length=255), nullable=False),
        sa.Column("calls_in", sa.Integer(), nullable=False),
        sa.Column("calls_out", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("date", "responsible_id", name="uq_operator_calls_daily_grain"),
    )
    op.create_index(op.f("ix_operator_calls_daily_date"), "operator_calls_daily", ["date"])


def downgrade() -> None:
    op.drop_index(op.f("ix_operator_calls_daily_date"), table_name="operator_calls_daily")
    op.drop_table("operator_calls_daily")
