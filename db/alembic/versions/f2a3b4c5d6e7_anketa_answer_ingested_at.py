"""Anketa: javob darajasidagi ingest belgisi + erkin qatnashchilar

1) anketa_answers.ingested_at — bilim bazasiga yuklash endi sessiya emas, JAVOB
darajasida kuzatiladi: tugallanmagan (in_progress) anketani ham qisman yuklash
va keyin faqat yangi javoblarni qo'shib yuklash mumkin. Backfill: allaqachon
yuklangan sessiyalarning javoblari belgilab qo'yiladi (dublikat bo'lmasin).

2) uq_anketa_assignment_toplam olib tashlanadi — qatnashchilar endi erkin
tanlanadi (hamma/lavozim/rol); 5 kishidan ko'p guruhda to'plamlar 1-5 aylanib
takrorlanadi, shuning uchun (session_id, toplam) unique bo'la olmaydi.

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-07-17
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f2a3b4c5d6e7"
down_revision: Union[str, None] = "e1f2a3b4c5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("anketa_answers", sa.Column("ingested_at", sa.DateTime(), nullable=True))
    with op.batch_alter_table("anketa_assignments") as batch:
        batch.drop_constraint("uq_anketa_assignment_toplam", type_="unique")
    # Backfill: knowledge_entries'da session_id bilan turgan (ya'ni allaqachon
    # yuklangan) sessiyalarning javoblarini belgilaymiz
    op.execute(
        """
        UPDATE anketa_answers SET ingested_at = CURRENT_TIMESTAMP
        WHERE assignment_id IN (
            SELECT id FROM anketa_assignments WHERE session_id IN (
                SELECT DISTINCT session_id FROM knowledge_entries
                WHERE session_id IS NOT NULL
            )
        )
        """
    )


def downgrade() -> None:
    with op.batch_alter_table("anketa_assignments") as batch:
        batch.create_unique_constraint("uq_anketa_assignment_toplam", ["session_id", "toplam"])
    op.drop_column("anketa_answers", "ingested_at")
