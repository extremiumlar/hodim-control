"""add positions table and users.position_id

Revision ID: b3d1a7c45e02
Revises: 9ee736a34dc8
Create Date: 2026-07-04 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3d1a7c45e02'
down_revision: Union[str, None] = '9ee736a34dc8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "positions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("menu_flags", sa.JSON(), nullable=True),
        sa.Column("metrics", sa.JSON(), nullable=True),
        sa.Column("managed_by_roles", sa.JSON(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("position_id", sa.Integer(), nullable=True))
        batch_op.create_index(op.f("ix_users_position_id"), ["position_id"], unique=False)
        batch_op.create_foreign_key(
            "fk_users_position_id_positions", "positions", ["position_id"], ["id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_constraint("fk_users_position_id_positions", type_="foreignkey")
        batch_op.drop_index(op.f("ix_users_position_id"))
        batch_op.drop_column("position_id")

    op.drop_table("positions")
