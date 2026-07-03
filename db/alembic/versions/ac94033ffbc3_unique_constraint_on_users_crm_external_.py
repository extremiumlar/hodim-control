"""unique constraint on users.crm_external_id

Revision ID: ac94033ffbc3
Revises: 46f433218e51
Create Date: 2026-07-03 21:38:17.258078

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ac94033ffbc3'
down_revision: Union[str, None] = '46f433218e51'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # batch mode SQLite'da ham, PostgreSQL'da ham ishlaydi (indeks almashtirish uchun).
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_index(op.f("ix_users_crm_external_id"))
        batch_op.create_index(
            op.f("ix_users_crm_external_id"), ["crm_external_id"], unique=True
        )


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_index(op.f("ix_users_crm_external_id"))
        batch_op.create_index(
            op.f("ix_users_crm_external_id"), ["crm_external_id"], unique=False
        )
