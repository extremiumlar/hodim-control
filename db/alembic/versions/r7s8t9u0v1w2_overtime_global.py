"""overtime_profiles: global default profil + auto_approve (§3.2)

Revision ID: r7s8t9u0v1w2
Revises: p5q6r7s8t9u0
Create Date: 2026-08-15

NEGA: `OvertimeProfile` FAQAT xodim bo'yicha edi (`user_id` unique, NOT NULL)
va `enabled` default `False`. Ya'ni HR har bir xodimga QO'LDA profil
yaratmaguncha qo'shimcha ish umuman hisoblanmasdi — jonli bazada
`enabled=true` profillar soni 0 edi va «avtomat hisoblansin» talabi shu
sababdan bajarilmayotgan edi.

Endi `FinePolicy` dagi bilan bir xil naqsh: `scope='global'` qatori
BARCHA xodimga default bo'lib xizmat qiladi, xodim qatori esa uni bosadi
(`resolve_overtime_profile`).

⚠️ MAVJUD INDEKSLARGA TEGILMAYDI (2026-08-15 da o'rganilgan dars). Birinchi
variantda eski indeksni `try/except` bilan o'chirishga urinilgan edi —
SQLite'da bu zararsiz, Postgres'da esa BUTUN TRANZAKSIYANI bekor qiladi
(`InFailedSQLTransactionError`) va migratsiya jonli bazada yiqilib qoldi.
Aslida eski `UNIQUE(user_id)` cheklovi bizga xalaqit ham bermaydi: ikkala
bazada ham NULL'lar bir-biridan farqli hisoblanadi, ya'ni `user_id IS NULL`
bo'lgan global qator unga umuman to'qnashmaydi.

Global qatorning BITTA bo'lishini esa alohida QISMAN unikal indeks
kafolatlaydi.

`down_revision` ATAYLAB `p5q6r7s8t9u0` (parallel ish `q6r7s8t9u0v1` ni
o'sha nuqtadan tortgan) — ikki bosh hosil bo'ladi, shuning uchun deploy'da
`alembic upgrade heads` (ko'plikda) ishlatiladi.
"""
from alembic import op
import sqlalchemy as sa

revision = "r7s8t9u0v1w2"
down_revision = "p5q6r7s8t9u0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # `batch_alter_table` — SQLite'da ustun turini o'zgartirish uchun shart
    # (jadval qayta yaratiladi); Postgres'da oddiy ALTER'ga aylanadi.
    with op.batch_alter_table("overtime_profiles") as batch:
        batch.add_column(
            sa.Column("scope", sa.String(10), nullable=False, server_default="user")
        )
        # Tasdiqni avtomatlashtirish — default O'CHIQ (pul xavfsizligi:
        # tasdiqsiz summa payslip'ga kirmasin). HR xohlagan xodimga yoqadi.
        batch.add_column(
            sa.Column(
                "auto_approve", sa.Boolean(), nullable=False, server_default=sa.false()
            )
        )
        # Global qator uchun `user_id` NULL bo'lishi kerak.
        batch.alter_column("user_id", existing_type=sa.Integer(), nullable=True)

    # Global qator FAQAT BITTA bo'lsin. Oddiy UNIQUE buni kafolatlamaydi:
    # NULL'lar farqli hisoblanadi, ya'ni bir nechta global qator sig'ib
    # ketardi. Qisman indeksni ikkala baza ham qo'llab-quvvatlaydi.
    op.create_index(
        "uq_overtime_profiles_global",
        "overtime_profiles",
        ["scope"],
        unique=True,
        sqlite_where=sa.text("scope = 'global'"),
        postgresql_where=sa.text("scope = 'global'"),
    )


def downgrade() -> None:
    op.drop_index("uq_overtime_profiles_global", table_name="overtime_profiles")
    with op.batch_alter_table("overtime_profiles") as batch:
        batch.drop_column("auto_approve")
        batch.drop_column("scope")
