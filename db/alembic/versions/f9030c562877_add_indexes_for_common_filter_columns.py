"""add indexes for common filter columns

Revision ID: f9030c562877
Revises: ac94033ffbc3
Create Date: 2026-07-03 23:20:14.133968

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f9030c562877'
down_revision: Union[str, None] = 'ac94033ffbc3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("tasks") as batch_op:
        batch_op.create_index(op.f("ix_tasks_assigned_to"), ["assigned_to"])
        batch_op.create_index(op.f("ix_tasks_status"), ["status"])

    with op.batch_alter_table("norms") as batch_op:
        batch_op.create_index(op.f("ix_norms_user_id"), ["user_id"])

    with op.batch_alter_table("excused_days") as batch_op:
        batch_op.create_index(op.f("ix_excused_days_user_id"), ["user_id"])
        batch_op.create_index(op.f("ix_excused_days_date"), ["date"])

    with op.batch_alter_table("audit_logs") as batch_op:
        batch_op.create_index(op.f("ix_audit_logs_actor_id"), ["actor_id"])
        batch_op.create_index(op.f("ix_audit_logs_action"), ["action"])


def downgrade() -> None:
    with op.batch_alter_table("audit_logs") as batch_op:
        batch_op.drop_index(op.f("ix_audit_logs_action"))
        batch_op.drop_index(op.f("ix_audit_logs_actor_id"))

    with op.batch_alter_table("excused_days") as batch_op:
        batch_op.drop_index(op.f("ix_excused_days_date"))
        batch_op.drop_index(op.f("ix_excused_days_user_id"))

    with op.batch_alter_table("norms") as batch_op:
        batch_op.drop_index(op.f("ix_norms_user_id"))

    with op.batch_alter_table("tasks") as batch_op:
        batch_op.drop_index(op.f("ix_tasks_status"))
        batch_op.drop_index(op.f("ix_tasks_assigned_to"))
