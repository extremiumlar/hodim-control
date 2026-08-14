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


async def resolve_request_policy(db: AsyncSession, user: User, kind: str):
    """Ariza qoidasini topadi: user > position > global (`FinePolicy`
    naqshi). Hech biri bo'lmasa None — u holda zanjir yo'q, to'g'ridan
    to'g'ri HR hal qiladi (orqaga moslik)."""
    from db.models import FinePolicyScope, RequestPolicy

    rows = list(
        await db.scalars(
            select(RequestPolicy).where(RequestPolicy.is_active.is_(True))
        )
    )

    def match(scope: str, scope_id: int | None) -> object | None:
        # Aniq tur ustun turadi: `kind='vacation'` qoidasi `kind=NULL`
        # (barcha turlar) qoidasidan kuchliroq.
        exact = [r for r in rows if r.scope == scope and r.scope_id == scope_id and r.kind == kind]
        if exact:
            return exact[0]
        anyk = [r for r in rows if r.scope == scope and r.scope_id == scope_id and r.kind is None]
        return anyk[0] if anyk else None

    return (
        match(FinePolicyScope.user.value, user.id)
        or match(FinePolicyScope.position.value, user.position_id)
        or match(FinePolicyScope.global_.value, None)
    )


async def leave_balance(db: AsyncSession, user: User, year: int, annual_days: int) -> dict:
    """Ta'til balansi — MASLAHAT sifatida (arizani BLOKLAMAYDI).

    Nega bloklamaydi: `hire_date` migratsiyada stavka sanasidan TAXMINAN
    to'ldirilgan va noto'g'ri bo'lishi mumkin. Noto'g'ri sana butun oqimni
    to'xtatib qo'ymasligi kerak — HR ko'radi va o'zi qaror qiladi.

    Ishlatilgan kunlar TASDIQLANGAN ARIZALARDAN sanaladi (`ExcusedDay` dan
    EMAS): u kasallikni ham qamraydi va natija noto'g'ri chiqardi."""
    from db.models import RequestKind, RequestStatus, EmployeeRequest

    start, end = date(year, 1, 1), date(year, 12, 31)
    rows = list(
        await db.scalars(
            select(EmployeeRequest).where(
                EmployeeRequest.user_id == user.id,
                EmployeeRequest.kind == RequestKind.vacation.value,
                EmployeeRequest.status == RequestStatus.approved.value,
                EmployeeRequest.start_date.isnot(None),
                EmployeeRequest.start_date >= start,
                EmployeeRequest.start_date <= end,
            )
        )
    )
    used = 0
    for r in rows:
        days = await range_days(db, user, r.start_date, r.end_date or r.start_date)
        used += sum(1 for d in days if d["is_working"])

    # Staj: hire_date bo'lsa shu yildagi ulushi (yil o'rtasida ishga
    # kirgan xodimga to'liq norma berilmaydi).
    entitled = annual_days
    if user.hire_date and user.hire_date > start:
        remaining_months = max(0, 12 - user.hire_date.month + 1)
        entitled = round(annual_days * remaining_months / 12)

    return {
        "year": year,
        "entitled_days": entitled,
        "used_days": used,
        "remaining_days": max(0, entitled - used),
        "hire_date": user.hire_date,
        # `hire_date` yo'q bo'lsa staj hisoblanmadi — UI shuni aytadi.
        "estimated": user.hire_date is None,
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
