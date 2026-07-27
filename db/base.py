import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./app.db")

# SQLite busy timeout: cPanel deploy'da bazaga IKKI jarayon yozadi (Passenger'dagi
# API + har daqiqalik cron_tick, jumladan in-process lid snapshot). Standart 5s
# qulf kutish qisqa yozuvlar to'qnashganda "database is locked" berishi mumkin —
# 30s ga oshiramiz (lokalda ham zarari yo'q).
_connect_args = {"timeout": 30} if DATABASE_URL.startswith("sqlite") else {}

engine = create_async_engine(DATABASE_URL, echo=False, connect_args=_connect_args)
async_session = async_sessionmaker(engine, expire_on_commit=False)

# SQLite standart holatda FOREIGN KEY cheklovlarini MAJBURLAMAYDI — ondelete=CASCADE
# ishlamaydi va foydalanuvchi o'chirilganda bog'liq yozuvlar (davomat, ish jadvali,
# soatlik reja va h.k.) yetim qolar edi. Har yangi ulanishda PRAGMA bilan yoqamiz.
# PostgreSQL'da kerak emas — u FK'ni o'zi majburlaydi.
if DATABASE_URL.startswith("sqlite"):

    @event.listens_for(engine.sync_engine, "connect")
    def _sqlite_pragmas(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        # WAL: standart "delete" jurnalida BITTA yozuvchi BARCHA o'quvchilarni
        # bloklaydi. cPanel'da bu jonli nosozlikka olib keldi: cron_tick ichidagi
        # og'ir lid skaneri (daqiqalab yozadi) paytida Passenger'ning YAGONA
        # ishchisi o'qish uchun qulf kutib qotib qolar, natijada sayt/bot/health
        # butunlay javob bermay qolardi. WAL'da o'quvchi va yozuvchi bir-birini
        # bloklamaydi. Bu baza faylining doimiy xossasi — bir marta o'rnatiladi.
        cursor.execute("PRAGMA journal_mode=WAL")
        # Qisqa yozuvlar to'qnashganda "database is locked" bermasin (connect_args
        # timeout=30 bilan bir xil — ba'zi drayverlarda faqat PRAGMA hisobga olinadi).
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()


class Base(DeclarativeBase):
    pass


async def get_session() -> AsyncSession:
    async with async_session() as session:
        yield session
