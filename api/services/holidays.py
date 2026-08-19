"""Bayram kunlari — ish kuni hisobining YAGONA istisnosi (yangi TZ 2.9 / S-09).

MUAMMO
──────
Tizim bayramni oddiy ish kuni deb sanardi. Oqibati ikki tomonlama va
ikkalasi ham xodimga qarshi ishlardi:
  • xodim kelmagani uchun kun «kelmagan» bo'lib ushlanmaga tushardi;
  • kunlik norma o'sha kunga ham qo'yilib, bajarilmagan ko'rinardi.

USTUVORLIK: override > BAYRAM > haftalik jadval > default (Du–Ju).
Ya'ni bayram umumiy jadvaldan kuchli, lekin xodimga ATAYIN qo'yilgan
kunlik override'dan kuchsiz — bayramda navbatchilikka chiqadigan xodim
bo'lishi mumkin va bu qaror HR tomonidan aniq kiritilgan.

⚠️ O'TGAN DAVRLARGA TEGMAYDI. Bayram ish kunini kamaytirgani uchun norma
va oylik prorata o'zgaradi; allaqachon tasdiqlangan oylikni qaytadan
hisoblash tarixni buzadi. HR yangi bayramni kiritsa u faqat joriy va
kelajak davrlarga ta'sir qiladi (o'tgan davr `payroll` da qulflangan).
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Holiday


async def holiday_dates(db: AsyncSession, start: date, end: date) -> set[date]:
    """[start, end] oralig'idagi bayram sanalari (ikki chegara ham kiradi).

    To'plam qaytariladi — chaqiruvchi kunlarni Pythonda aylanib chiqadi,
    ya'ni har kun uchun alohida so'rov yo'q (`month_schedule` naqshi)."""
    rows = await db.scalars(
        select(Holiday.date).where(Holiday.date >= start, Holiday.date <= end)
    )
    return set(rows)


async def is_holiday(db: AsyncSession, d: date) -> bool:
    """Bitta kun uchun — check-in kabi yakka tekshiruvlarda."""
    return bool(await db.scalar(select(Holiday.id).where(Holiday.date == d).limit(1)))


async def missing_year(db: AsyncSession, year: int) -> bool:
    """Shu yilga bironta ham bayram kiritilmaganmi (dekabr eslatmasi uchun)."""
    row = await db.scalar(
        select(Holiday.id)
        .where(Holiday.date >= date(year, 1, 1), Holiday.date <= date(year, 12, 31))
        .limit(1)
    )
    return row is None
