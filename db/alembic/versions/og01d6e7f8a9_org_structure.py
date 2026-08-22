"""S-39: tashkiliy tuzilma (yangi TZ 3.16).

⚠️ `positions.parent_position_id` — FK modelda e'lon qilinadi, bu
yerda oddiy `Integer`. Loyiha naqshi (`av02b2c3d4e5_advance_issued`):
SQLite `batch_alter_table` NOMSIZ FK bilan yiqiladi
(«Constraint must have a name»).

Revision ID: og01d6e7f8a9
Revises: cr05c5d6e7f8
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "og01d6e7f8a9"
down_revision = "cr05c5d6e7f8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("positions") as b:
        b.add_column(sa.Column("parent_position_id", sa.Integer(), nullable=True))
    op.create_index(
        "ix_positions_parent_position_id", "positions", ["parent_position_id"]
    )

    op.create_table(
        "job_descriptions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "position_id",
            sa.Integer(),
            sa.ForeignKey("positions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("purpose", sa.Text(), nullable=True),
        sa.Column("duties", sa.JSON(), nullable=True),
        sa.Column("rights", sa.JSON(), nullable=True),
        sa.Column("responsibility", sa.JSON(), nullable=True),
        sa.Column("requirements", sa.JSON(), nullable=True),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        #  ⚠️ Bir lavozimda bir versiya IKKI marta bo'lmaydi — bu
        #  «tahrirlash o'rniga yangi versiya» qoidasini BAZADA
        #  majburlaydi.
        sa.UniqueConstraint("position_id", "version", name="uq_job_description_version"),
    )
    op.create_index("ix_job_descriptions_position_id", "job_descriptions", ["position_id"])
    op.create_index("ix_job_descriptions_version", "job_descriptions", ["version"])

    op.create_table(
        "company_profile",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("mission", sa.Text(), nullable=True),
        sa.Column("values", sa.JSON(), nullable=True),
        sa.Column("goals", sa.JSON(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("company_profile")
    op.drop_table("job_descriptions")
    op.drop_index("ix_positions_parent_position_id", table_name="positions")
    with op.batch_alter_table("positions") as b:
        b.drop_column("parent_position_id")
