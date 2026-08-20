"""ikki shoxni birlashtirish: mol-mulk tarixi + avans sozlamalari

Revision ID: mg01f6a7b8c9
Revises: as02c3d4e5f6, av05e5f6a7b8
Create Date: 2026-08-20

Ikki ish parallel olib borildi va ikkalasi ham `av04d4e5f6a7` dan
shoxlandi: `as02c3d4e5f6` (mol-mulk) va `av05e5f6a7b8` (avans
sozlamalari). Ular bir-biriga tegmaydi — faqat birlashtirish kerak,
hech qanday DDL yo'q.
"""

revision = "mg01f6a7b8c9"
down_revision = ("as02c3d4e5f6", "av05e5f6a7b8")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
