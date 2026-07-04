from datetime import date, datetime
from zoneinfo import ZoneInfo

from api.config import settings

TASHKENT_TZ = ZoneInfo(settings.timezone)


def today_local() -> date:
    """Joriy sanani serverning UTC vaqti emas, `settings.timezone` (Asia/Tashkent)
    bo'yicha qaytaradi — kun chegarasi mahalliy vaqt bo'yicha to'g'ri bo'lishi uchun."""
    return datetime.now(TASHKENT_TZ).date()


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
