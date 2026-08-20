"""Merge: acknowledgements (S-20) + advance_responses (Avans TZ)

Revision ID: mg02a1b2c3d4
Revises: ak01c3d4e5f6, av07b8c9d0e1
Create Date: 2026-08-20

NEGA: ikki parallel seans bir vaqtda `av06a7b8c9d0` dan tarmoqlandi.
Birortasining zanjirini qayta ulash mumkin emas — ikkala migratsiya ham
lokal bazaga ALLAQACHON qo'llangan, ya'ni `alembic_version` da ikkita
qator turibdi. Merge ularni bitta head'ga yig'adi va hech qanday DDL
bajarmaydi.
"""
from alembic import op  # noqa: F401
import sqlalchemy as sa  # noqa: F401

revision = "mg02a1b2c3d4"
down_revision = ("ak01c3d4e5f6", "av07b8c9d0e1")
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Faqat birlashtirish — o'zgarish yo'q."""


def downgrade() -> None:
    """Faqat birlashtirish — o'zgarish yo'q."""
