"""group_post_config.last_posted_contracts — digestdagi shartnoma jami

Kechqurungi digest ko'rsatgan «🤝 shartnoma» jami saqlanadi; ertasi ertalabki
"kecha yakuni" tuzatish xabari yakuniy son bilan aynan shuni solishtiradi
(qo'ng'iroq/tashrif uchun `b8c9d0e1f2a3` da qilinganidek).

Revision ID: k0l1m2n3o4p5
Revises: j9k0l1m2n3o4
Create Date: 2026-08-14
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "k0l1m2n3o4p5"
down_revision: Union[str, None] = "j9k0l1m2n3o4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "group_post_config", sa.Column("last_posted_contracts", sa.Integer(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("group_post_config", "last_posted_contracts")
