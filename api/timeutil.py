from datetime import date, datetime
from zoneinfo import ZoneInfo

from api.config import settings

TASHKENT_TZ = ZoneInfo(settings.timezone)


def today_local() -> date:
    """Joriy sanani serverning UTC vaqti emas, `settings.timezone` (Asia/Tashkent)
    bo'yicha qaytaradi — kun chegarasi mahalliy vaqt bo'yicha to'g'ri bo'lishi uchun."""
    return datetime.now(TASHKENT_TZ).date()
