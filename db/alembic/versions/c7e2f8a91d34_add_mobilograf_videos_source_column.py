"""add mobilograf_videos.source and make telegram fields nullable

Revision ID: c7e2f8a91d34
Revises: b3d1a7c45e02
Create Date: 2026-07-04 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c7e2f8a91d34'
down_revision: Union[str, None] = 'b3d1a7c45e02'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("mobilograf_videos") as batch_op:
        batch_op.add_column(
            sa.Column("source", sa.String(length=20), nullable=False, server_default="telegram_reaction")
        )
        # Qo'lda kiritilgan ("manual") yozuvlarda Telegram xabari bo'lmaydi — NULL.
        batch_op.alter_column("telegram_message_id", existing_type=sa.Integer(), nullable=True)
        batch_op.alter_column("group_chat_id", existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    op.execute("DELETE FROM mobilograf_videos WHERE source = 'manual'")
    with op.batch_alter_table("mobilograf_videos") as batch_op:
        batch_op.alter_column("group_chat_id", existing_type=sa.Integer(), nullable=False)
        batch_op.alter_column("telegram_message_id", existing_type=sa.Integer(), nullable=False)
        batch_op.drop_column("source")
