"""request_policies — ariza tasdiqlash zanjiri qoidalari

ARIZALAR_REJASI.md Bosqich 4. Chegaralar KODDA emas, bazada: HR dasturchi
yordamisiz «rahbarlarga 30 kun, qolganlarga 21» deya oladi.

`FinePolicy` scoping naqshi ayni holicha ko'chirildi (global > position >
user prioriteti) — yangi «Global Settings» dvigateli qurilmadi, chunki
loyihada bu vazifani bajaradigan tayyor va sinalgan naqsh bor.

Boshlang'ich qator: GLOBAL, barcha turlar uchun — bevosita rahbar tasdig'i
YOQIQ (xodimda `manager_id` bo'lsa), ta'til 7 kundan oshsa va avans
2 000 000 so'mdan oshsa Boshliq ham tasdiqlaydi (8-bo'lim defaultlari).

Revision ID: l1m2n3o4p5q6
Revises: i8j9k0l1m2n3
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "l1m2n3o4p5q6"
down_revision: Union[str, None] = "i8j9k0l1m2n3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "request_policies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("scope", sa.String(length=20), nullable=False, server_default="global"),
        sa.Column("scope_id", sa.Integer(), nullable=True),
        sa.Column("kind", sa.String(length=20), nullable=True),
        sa.Column("requires_manager", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("boss_threshold_days", sa.Integer(), nullable=True),
        sa.Column("boss_threshold_amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("scope", "scope_id", "kind", name="uq_request_policy_scope_kind"),
    )
    op.create_index("ix_request_policies_scope", "request_policies", ["scope", "scope_id"])

    # Boshlang'ich global qoida — tizim qoidasiz qolmasin (aks holda har
    # ariza «zanjirsiz» ketardi va Bosqich 4 ning ma'nosi bo'lmasdi).
    op.execute(
        """
        INSERT INTO request_policies
            (scope, scope_id, kind, requires_manager,
             boss_threshold_days, boss_threshold_amount, is_active, updated_at)
        VALUES ('global', NULL, NULL, true, 7, 2000000, true, CURRENT_TIMESTAMP)
        """
    )


def downgrade() -> None:
    op.drop_index("ix_request_policies_scope", table_name="request_policies")
    op.drop_table("request_policies")
