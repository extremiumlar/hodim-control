"""verifix (hodim_crm) davomatini yagona backendga birlashtirish:
attendance + office_locations jadvallari va users.face_* ustunlari.

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-07-14 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a7b8c9d0e1f2"
down_revision: Union[str, None] = "f6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "office_locations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("latitude", sa.Numeric(9, 6), nullable=False),
        sa.Column("longitude", sa.Numeric(9, 6), nullable=False),
        sa.Column("radius_meters", sa.Integer(), nullable=False, server_default="150"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "attendance",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id", sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("check_in_time", sa.DateTime(), nullable=True),
        sa.Column("check_in_lat", sa.Numeric(9, 6), nullable=True),
        sa.Column("check_in_lng", sa.Numeric(9, 6), nullable=True),
        sa.Column("check_in_distance_m", sa.Integer(), nullable=True),
        sa.Column("check_out_time", sa.DateTime(), nullable=True),
        sa.Column("check_out_lat", sa.Numeric(9, 6), nullable=True),
        sa.Column("check_out_lng", sa.Numeric(9, 6), nullable=True),
        sa.Column("late_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("early_leave_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("worked_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="present"),
        sa.Column("is_weekend", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("user_id", "date", name="uq_attendance_user_date"),
    )
    op.create_index("ix_attendance_user_id", "attendance", ["user_id"])
    op.create_index("ix_attendance_date", "attendance", ["date"])
    op.create_index("ix_attendance_status", "attendance", ["status"])

    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("face_descriptor", sa.Text(), nullable=True))
        batch.add_column(sa.Column("face_registered_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_column("face_registered_at")
        batch.drop_column("face_descriptor")
    op.drop_index("ix_attendance_status", table_name="attendance")
    op.drop_index("ix_attendance_date", table_name="attendance")
    op.drop_index("ix_attendance_user_id", table_name="attendance")
    op.drop_table("attendance")
    op.drop_table("office_locations")
