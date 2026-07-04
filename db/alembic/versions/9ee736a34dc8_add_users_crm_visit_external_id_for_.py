"""add users.crm_visit_external_id for uysot lead-based visit tracking

Revision ID: 9ee736a34dc8
Revises: f9030c562877
Create Date: 2026-07-04 01:19:27.424060

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9ee736a34dc8'
down_revision: Union[str, None] = 'f9030c562877'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("crm_visit_external_id", sa.String(length=64), nullable=True))
        batch_op.create_index(
            op.f("ix_users_crm_visit_external_id"), ["crm_visit_external_id"], unique=True
        )


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_index(op.f("ix_users_crm_visit_external_id"))
        batch_op.drop_column("crm_visit_external_id")
