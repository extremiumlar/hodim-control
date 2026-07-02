"""phase3: crm_external_id and unique constraints

Revision ID: 46f433218e51
Revises: 6acf535ebaf6
Create Date: 2026-07-02 16:04:18.138106

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '46f433218e51'
down_revision: Union[str, None] = '6acf535ebaf6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # batch mode SQLite'da ham, PostgreSQL'da ham ishlaydi (constraint qo'shish uchun).
    with op.batch_alter_table("bonuses") as batch_op:
        batch_op.create_unique_constraint("uq_bonuses_user_period", ["user_id", "period"])

    with op.batch_alter_table("daily_results") as batch_op:
        batch_op.create_unique_constraint("uq_daily_results_user_date", ["user_id", "date"])

    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("crm_external_id", sa.String(length=64), nullable=True))
        batch_op.create_index(op.f("ix_users_crm_external_id"), ["crm_external_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_index(op.f("ix_users_crm_external_id"))
        batch_op.drop_column("crm_external_id")

    with op.batch_alter_table("daily_results") as batch_op:
        batch_op.drop_constraint("uq_daily_results_user_date", type_="unique")

    with op.batch_alter_table("bonuses") as batch_op:
        batch_op.drop_constraint("uq_bonuses_user_period", type_="unique")
