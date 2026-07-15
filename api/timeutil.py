from datetime import date, datetime
from zoneinfo import ZoneInfo

from api.config import settings

TASHKENT_TZ = ZoneInfo(settings.timezone)


def today_local() -> date:
    """Joriy sanani serverning UTC vaqti emas, `settings.timezone` (Asia/Tashkent)
    bo'yicha qaytaradi — kun chegarasi mahalliy vaqt bo'yicha to'g'ri bo'lishi uchun."""
    return datetime.now(TASHKENT_TZ).date()


# Tushlik tanaffusi — ish daqiqalari hisobidan chiqariladi. YAGONA manba:
# soatlik reja (hourly_plan) ham, davomat worked_minutes (attendance servisi) ham
# shu qiymatlar va work_minutes'dan foydalanadi — "ishlangan vaqt" ta'rifi bitta.
LUNCH_START = 13 * 60  # 13:00
LUNCH_END = 14 * 60  # 14:00


def work_minutes(a: int, b: int) -> int:
    """[a, b) oralig'idagi ish daqiqalari — tushlik (13:00–14:00) ayirilgan holda."""
    if b <= a:
        return 0
    lunch_overlap = max(0, min(b, LUNCH_END) - max(a, LUNCH_START))
    return (b - a) - lunch_overlap


def local_range_utc_naive(day_from: date, day_to: date) -> tuple[datetime, datetime]:
    """[day_from 00:00, day_to+1 00:00) mahalliy oraliqni bazadagi naive-UTC
    (datetime.utcnow bilan yozilgan) ustunlar bilan solishtirish uchun naive UTC
    juftlikka o'giradi."""
    from datetime import time, timedelta, timezone

    start_local = datetime.combine(day_from, time.min, tzinfo=TASHKENT_TZ)
    end_local = datetime.combine(day_to + timedelta(days=1), time.min, tzinfo=TASHKENT_TZ)
    return (
        start_local.astimezone(timezone.utc).replace(tzinfo=None),
        end_local.astimezone(timezone.utc).replace(tzinfo=None),
    )
