"""ikki shoxni birlashtirish: e'lonlar moduli + avans e'lonlari

Revision ID: mg03b2c3d4e5
Revises: an01d4e5f6a7, av08c9d0e1f2
Create Date: 2026-08-20

Parallel ish: `an01d4e5f6a7` (e'lonlar moduli) va `av08c9d0e1f2`
(avans kuni e'lonlari) ikkalasi ham `mg02a1b2c3d4` dan shoxlangan.
Ular bir-biriga tegmaydi — faqat birlashtirish, DDL yo'q.

⚠️ NOMLAR O'XSHASH, LEKIN BOSHQA NARSA:
`announcements` — umumiy e'lonlar moduli (boshqa seans);
`advance_announcements` — avans kuni qachonligi haqidagi bir martalik
e'lon (Avans TZ D-01).
"""

revision = "mg03b2c3d4e5"
down_revision = ("an01d4e5f6a7", "av08c9d0e1f2")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
