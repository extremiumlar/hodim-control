"""`AuditLog.before/after` (JSON ustun) uchun xavfsiz turga o'girish.

NEGA ALOHIDA MODUL: bu yordamchi `admin_override.py` da yozilgan va o'sha
yerda ishlagan, lekin `payroll.py` uni bilmagani uchun o'z snapshot'ini xom
ORM qiymatlari bilan qurgan. Natijada jarima qoidasi va qo'shimcha ish
profilini TAHRIRLASH har safar 500 bergan (2026-08-08 tahlili, BUG-1):

    sqlalchemy.exc.StatementError: (builtins.TypeError)
    Object of type Decimal is not JSON serializable

Sabab: `AuditLog.before/after` — JSON ustun, SQLAlchemy unga oddiy
`json.dumps` qo'llaydi va `Decimal` (`Numeric` ustunlar) hamda `date`/
`datetime` turlarini tushunmaydi. Audit yozuvi commit paytida yiqilgani
uchun ASOSIY o'zgarish ham qaytarilardi — foydalanuvchi "saqlanmadi" degan
sababsiz xatoni ko'rardi.

Shuning uchun yordamchi bitta joyga chiqarildi: yangi endpoint yozgan odam
uni `admin_override` ichidan qidirib topishi shart emas.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any


def json_safe(value: Any) -> Any:
    """Bitta qiymatni JSON-xavfsiz turga o'giradi.

    `Enum` ham qamrab olingan: modellarda holat ustunlari satr sifatida
    saqlanadi, lekin kod ba'zan `Enum` a'zosini uzatadi va u ham
    `json.dumps` uchun begona.
    """
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, Enum):
        return value.value
    return value


def row_to_dict(row: Any, *, exclude: tuple[str, ...] = ()) -> dict:
    """ORM qatorini JSON-xavfsiz dict'ga — ustunlar ro'yxati bo'yicha.

    `exclude` — audit snapshot'iga kerak bo'lmagan ustunlar (masalan "id":
    u o'zgarmaydi va farqni ko'rsatmaydi).
    """
    return {
        c.name: json_safe(getattr(row, c.name))
        for c in row.__table__.columns
        if c.name not in exclude
    }
