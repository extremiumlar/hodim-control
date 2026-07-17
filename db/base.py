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
    def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


class Base(DeclarativeBase):
    pass


async def get_session() -> AsyncSession:
    async with async_session() as session:
        yield session
