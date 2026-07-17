"""Sotuv playbook jadvallari (build jarayoni + yozuvlar)

Sotuvchilar uslubini o'rganish (2-bosqich): anketa javoblari + real natijalar
(daily_results) + operator sabablari (shortfall_reason) dan AI "vaziyat →
texnika → iboralar" playbook'ini quradi; Boss tasdig'idan keyin sotuv AI
(3-bosqich) foydalanadi.

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
Create Date: 2026-07-17
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e1f2a3b4c5d6"
down_revision: Union[str, None] = "d0e1f2a3b4c5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "playbook_builds",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="profiles"),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("ai_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_playbook_builds_status", "playbook_builds", ["status"])

    op.create_table(
        "playbook_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "build_id",
            sa.Integer(),
            sa.ForeignKey("playbook_builds.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("kind", sa.String(length=10), nullable=False, server_default="etiroz"),
        sa.Column("situation", sa.Text(), nullable=False),
        sa.Column("technique", sa.Text(), nullable=False),
        sa.Column("phrases", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="unverified"),
        sa.Column("verified_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("verified_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_playbook_entries_status", "playbook_entries", ["status"])


def downgrade() -> None:
    op.drop_index("ix_playbook_entries_status", table_name="playbook_entries")
    op.drop_table("playbook_entries")
    op.drop_index("ix_playbook_builds_status", table_name="playbook_builds")
    op.drop_table("playbook_builds")
