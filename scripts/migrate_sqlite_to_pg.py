"""SQLite -> PostgreSQL ma'lumot ko'chirish (bir martalik migratsiya).

Ishlatilishi (serverda):
    export PG_URL='postgresql+asyncpg://user:parol@localhost/baza'
    venv/bin/python scripts/migrate_sqlite_to_pg.py --sqlite /tmp/snapshot.db --wipe

Qanday ishlaydi:
  - Jadvallar db.models metadata'sining FK-xavfsiz tartibida (sorted_tables)
    ko'chiriladi — bola jadval hech qachon ota jadvaldan oldin yozilmaydi.
  - SQLite'dan o'qish SQLAlchemy jadval tiplari orqali — sana/bool/JSON
    qiymatlar to'g'ri Python tiplariga aylanib, PG'ga to'g'ri yoziladi.
  - ID'lar AYNAN saqlanadi; oxirida har jadvalning sequence'i max(id)+1 ga
    to'g'rilanadi (aks holda keyingi INSERT'lar "duplicate key" berardi).
  - alembic_version KO'CHIRILMAYDI — PG'da alembic upgrade head o'zi yozgan.
  - --wipe: PG jadvallarini avval tozalaydi (TRUNCATE ... CASCADE) — sinovni
    qayta-qayta ishga tushirish xavfsiz bo'lishi uchun.

Skript jonli SQLite'ga YOZMAYDI (faqat o'qiydi) — jonli tizimga ta'sir yo'q.
"""
import argparse
import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import func, select, text  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402

from db.base import Base  # noqa: E402
from db import models  # noqa: F401,E402 — metadata to'lishi uchun

CHUNK = 500


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sqlite", default=str(ROOT / "app.db"), help="SQLite fayl yo'li")
    ap.add_argument("--pg-url", default=os.getenv("PG_URL"), help="postgresql+asyncpg://... URL")
    ap.add_argument("--wipe", action="store_true", help="PG jadvallarini avval tozalash")
    args = ap.parse_args()
    if not args.pg_url:
        raise SystemExit("PG_URL berilmadi (--pg-url yoki muhit o'zgaruvchisi)")

    src = create_async_engine(f"sqlite+aiosqlite:///{args.sqlite}")
    dst = create_async_engine(args.pg_url)

    tables = [t for t in Base.metadata.sorted_tables]
    print(f"{len(tables)} jadval ko'chiriladi ({Path(args.sqlite).name} -> PG)")

    if args.wipe:
        async with dst.begin() as conn:
            names = ", ".join(f'"{t.name}"' for t in tables)
            await conn.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))
        print("PG jadvallari tozalandi (--wipe)")

    mismatch = []
    async with src.connect() as sc:
        for table in tables:
            rows = [dict(r) for r in (await sc.execute(select(table))).mappings().all()]

            # ── Yetim FK tozalash ──────────────────────────────────────────────
            # SQLite'da FK'lar tarixan majburlanmagan (masalan foydalanuvchi
            # majburiy o'chirilganda audit_logs.target_user_id yetim qolgan) —
            # PG esa qat'iy. Ota jadvallar sorted_tables tufayli allaqachon
            # ko'chirilgan, shuning uchun mavjud ID'larni o'sha yerdan o'qiymiz.
            # Nullable ustun -> NULL (yozuv saqlanadi); NOT NULL -> aniq xato
            # bilan to'xtaymiz (jimgina satr o'chirish YO'Q).
            for fk in table.foreign_keys:
                col = fk.parent
                ref_table, ref_col = fk.column.table, fk.column
                if ref_table is table:
                    parent_ids = {r[ref_col.name] for r in rows}
                else:
                    async with dst.connect() as dc:
                        parent_ids = set(
                            (await dc.execute(select(ref_col))).scalars().all()
                        )
                orphans = [
                    r for r in rows if r[col.name] is not None and r[col.name] not in parent_ids
                ]
                if not orphans:
                    continue
                if not col.nullable:
                    raise SystemExit(
                        f"YETIM (NOT NULL!): {table.name}.{col.name} -> {ref_table.name} "
                        f"({len(orphans)} satr, misol id={orphans[0].get('id')}) — qo'lda qaror kerak"
                    )
                for r in orphans:
                    r[col.name] = None
                print(
                    f"  yetim tozalandi: {table.name}.{col.name} -> {ref_table.name}: "
                    f"{len(orphans)} satr NULL qilindi"
                )

            if rows:
                async with dst.begin() as dc:
                    for i in range(0, len(rows), CHUNK):
                        await dc.execute(table.insert(), rows[i : i + CHUNK])

            # Tekshiruv: satr soni ikkala tomonda bir xilmi
            async with dst.connect() as dc:
                dst_n = (await dc.execute(select(func.count()).select_from(table))).scalar()
            status = "OK " if dst_n == len(rows) else "XATO"
            if dst_n != len(rows):
                mismatch.append(table.name)
            print(f"  {status} {table.name}: sqlite={len(rows)} pg={dst_n}")

    # Sequence'larni to'g'rilash (id ustuni bor jadvallarda)
    async with dst.begin() as dc:
        for table in tables:
            if "id" in table.c and table.c.id.autoincrement is not False:
                await dc.execute(
                    text(
                        f"SELECT setval(pg_get_serial_sequence('\"{table.name}\"','id'), "
                        f"COALESCE((SELECT MAX(id) FROM \"{table.name}\"), 0) + 1, false)"
                    )
                )
    print("Sequence'lar to'g'rilandi")

    await src.dispose()
    await dst.dispose()

    if mismatch:
        raise SystemExit(f"MOS KELMADI: {mismatch}")
    print("HAMMASI MOS — ko'chirish muvaffaqiyatli")


if __name__ == "__main__":
    asyncio.run(main())
