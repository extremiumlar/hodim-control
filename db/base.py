import json
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


def _json_default(value):
    """JSON ustunlar uchun ZAXIRA o'girish (`Decimal`/`date`/`Enum`).

    NEGA KERAK (2026-08-08, BUG-1 saboqlari): `AuditLog.before/after`,
    `Payslip.breakdown` kabi JSON ustunlarga SQLAlchemy oddiy `json.dumps`
    qo'llaydi. Kod tasodifan `Decimal` (Numeric ustun) yoki `date` uzatsa,
    u yerda `TypeError: Object of type Decimal is not JSON serializable`
    chiqadi va COMMIT butunlay yiqiladi — ya'ni audit yozuvidagi kichik
    xato ASOSIY amalni (jarima qoidasini saqlash, oylik hisoblash) bekor
    qilardi. Aynan shu bug jonli tizimda topilgan.

    Chaqiruvchi tomonda `api/audit_json.py` bor va u ASOSIY yo'l bo'lib
    qoladi (u aniq, o'qiladigan qiymat beradi). Bu esa oxirgi to'siq: yangi
    kod uni ishlatishni unutsa, audit biroz noaniqroq yoziladi, LEKIN pul
    amali yiqilmaydi. Jim buzilishdan ko'ra jim tuzatish afzal.
    """
    from datetime import date as _date, datetime as _datetime
    from decimal import Decimal as _Decimal
    from enum import Enum as _Enum

    if isinstance(value, (_datetime, _date)):
        return value.isoformat()
    if isinstance(value, _Decimal):
        return float(value)
    if isinstance(value, _Enum):
        return value.value
    # Qolgan noma'lum tur — satrga. `raise` qilsak, yana o'sha 500 bo'lardi.
    return str(value)


def _json_serializer(obj) -> str:
    return json.dumps(obj, default=_json_default, ensure_ascii=False)


engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    connect_args=_connect_args,
    json_serializer=_json_serializer,
)
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
        # DIQQAT — WAL BU YERDA ISHLATILMAYDI (2026-07-27 jonli sinov):
        # journal_mode=WAL o'quvchi/yozuvchi to'qnashuvini yo'qotardi, LEKIN
        # cPanel'da Passenger ostida bazaga tegadigan HAR BIR so'rov 500 bera
        # boshladi (CLI'dan o'sha baza WAL'da muammosiz ochilardi — ya'ni web
        # jarayonining kontekstida WAL uchun zarur -wal/-shm yordamchi fayllari
        # yaratilmadi). Sayt butunlay ishlamay qolgani uchun qaytarib olindi.
        # Qulf to'qnashuvi o'rniga cron yukini kamaytirish yo'li tanlandi
        # (9e4adc8: lid skaneri 30 daq, tick'lar siyraklashtirildi).
        # Qisqa yozuvlar to'qnashganda "database is locked" bermasin (connect_args
        # timeout=30 bilan bir xil — ba'zi drayverlarda faqat PRAGMA hisobga olinadi).
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()


class Base(DeclarativeBase):
    pass


async def get_session() -> AsyncSession:
    async with async_session() as session:
        yield session
