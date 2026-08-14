"""Oraliqdagi ish kunlari kalkulyatori (ARIZALAR_REJASI.md 3.6/2.2).

NEGA KERAK: xodim «1-sentabrdan 10-sentabrgacha ta'til» deb yozganda, u 10
kun so'radim deb o'ylaydi — aslida ularning bir qismi dam olish kuni bo'lishi
mumkin. Ariza yuborishdan OLDIN aniq raqamni ko'rsatish nizoning oldini
oladi: «10 kundan 8 tasi ish kuni».

Qoida MANBAI yangi emas: `override > haftalik > default (Du-Ju 09:00-18:00)`
— aynan `hourly_plan._effective_today` va `payroll.month_schedule` dagi
qoida. Bu yerda faqat ixtiyoriy ORALIQ uchun va BITTA bulk so'rov bilan
(kuniga alohida so'rov emas).

⚠️ GLOBAL BAYRAMLAR HISOBGA OLINMAYDI — `Holiday` jadvali hali yo'q
(egasining qaroriga ko'ra Bosqich 0 dan chiqarilgan). Bayram kuni xodimga
alohida `WorkScheduleOverride` bilan qo'yilgan bo'lsa, u to'g'ri hisoblanadi.
Jadval qo'shilganda shu funksiyaga 4-daraja (`override > holiday > weekly >
default`) qo'shiladi va u avtomatik uchala iste'molchiga tarqaladi.
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import ExcusedDay, ExcusedStatus, User, WorkScheduleOverride, WorkScheduleWeekly

# Oraliqning maksimal uzunligi — bir yildan uzun ta'til so'ralishi xato
# (masalan sana noto'g'ri terilgan) va 400 ta ExcusedDay yozib qo'yishdan
# himoya qiladi.
MAX_RANGE_DAYS = 366


async def range_days(db: AsyncSession, user: User, start: date, end: date) -> list[dict]:
    """[start, end] oraliqning har kuni: `{"date", "is_working"}`.

    Bulk: override va haftalik jadval BITTA so'rovda olinadi, kunlar
    Pythonda hisoblanadi (`payroll.month_schedule` naqshi)."""
    overrides = {
        o.date: o
        for o in await db.scalars(
            select(WorkScheduleOverride).where(
                WorkScheduleOverride.user_id == user.id,
                WorkScheduleOverride.date >= start,
                WorkScheduleOverride.date <= end,
            )
        )
    }
    weekly = {
        w.weekday: w
        for w in await db.scalars(
            select(WorkScheduleWeekly).where(WorkScheduleWeekly.user_id == user.id)
        )
    }

    out: list[dict] = []
    d = start
    while d <= end:
        ov = overrides.get(d)
        if ov is not None:
            is_working = ov.is_working
        else:
            w = weekly.get(d.weekday())
            is_working = w.is_working if w is not None else d.weekday() < 5
        out.append({"date": d, "is_working": is_working})
        d += timedelta(days=1)
    return out


async def calc_range(db: AsyncSession, user: User, start: date, end: date) -> dict:
    """Xodimga ko'rsatiladigan xulosa + to'qnashuv ogohlantirishi.

    Qaytaradi:
      total_days      — kalendar kunlar soni
      working_days    — shundan ish kunlari (ta'til shularga sarflanadi)
      off_days        — dam olish kunlari
      conflict_dates  — oraliqda ALLAQACHON tasdiqlangan sababli kun bo'lgan
                        sanalar (ariza ustma-ust tushmasin)
    """
    days = await range_days(db, user, start, end)
    working = [d["date"] for d in days if d["is_working"]]

    conflicts = [
        e.date
        for e in await db.scalars(
            select(ExcusedDay).where(
                ExcusedDay.user_id == user.id,
                ExcusedDay.date >= start,
                ExcusedDay.date <= end,
                ExcusedDay.status == ExcusedStatus.approved.value,
            )
        )
    ]

    return {
        "start_date": start,
        "end_date": end,
        "total_days": len(days),
        "working_days": len(working),
        "off_days": len(days) - len(working),
        "working_dates": working,
        "conflict_dates": sorted(conflicts),
    }


def human_summary(calc: dict) -> str:
    """Bot/sayt uchun bir qatorlik xulosa."""
    total, working, off = calc["total_days"], calc["working_days"], calc["off_days"]
    if off:
        return (
            f"{total} kun tanlandi, shundan {off} tasi dam olish kuni — "
            f"aslida {working} ish kuni uchun ta'til olyapsiz."
        )
    return f"{total} kun tanlandi — hammasi ish kuni."
