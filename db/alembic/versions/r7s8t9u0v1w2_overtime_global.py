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
(`resolve_overtime_profile`). Yangi ishga kirgan xodim ham avtomatik
qamrab olinadi — «tugmani yana bosishni unutish» xatosi mumkin emas.

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
    # `user_id` endi NULL bo'lishi mumkin (global qator uchun) va eski
    # unikal indeks o'rniga (scope, user_id) juftligi ishlatiladi.
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
        batch.alter_column("user_id", existing_type=sa.Integer(), nullable=True)

    # Eski unikal indeksni yangisi bilan almashtiramiz. Nomi muhitga qarab
    # farq qilishi mumkin — topilmasa jim o'tkazib yuboriladi (indeks
    # bo'lmasa ham yangi cheklovlar to'g'ri ishlaydi).
    for nom in ("ix_overtime_profiles_user_id", "uq_overtime_profiles_user_id"):
        try:
            op.drop_index(nom, table_name="overtime_profiles")
        except Exception:  # noqa: BLE001 — indeks yo'q bo'lsa muammo emas
            pass

    op.create_index(
        "ix_overtime_profiles_user_id", "overtime_profiles", ["user_id"], unique=False
    )
    # Xodim bo'yicha bitta qator (avvalgi kafolat saqlanadi).
    op.create_index(
        "uq_overtime_profiles_user",
        "overtime_profiles",
        ["user_id"],
        unique=True,
        sqlite_where=sa.text("user_id IS NOT NULL"),
        postgresql_where=sa.text("user_id IS NOT NULL"),
    )
    # Global qator FAQAT BITTA bo'lishi kerak. Oddiy UNIQUE(user_id) buni
    # kafolatlamaydi: ikkala bazada ham NULL'lar bir-biridan FARQLI
    # hisoblanadi, ya'ni bir nechta global qator sig'ib ketardi.
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
    op.drop_index("uq_overtime_profiles_user", table_name="overtime_profiles")
    with op.batch_alter_table("overtime_profiles") as batch:
        batch.drop_column("auto_approve")
        batch.drop_column("scope")
