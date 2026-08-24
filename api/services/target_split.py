"""Oylik targetni xodimlarga tarqatish — voronka 5-bosqich.

Reja: `VORONKA_TARGET_REJASI.html` 05-bosqich — «eng qimmatli bog'lanish:
oylik voronka targeti mavjud NORMA tizimiga ulanadi».

QANDAY BO'LINADI: oylik raqam (kerakli tashrif / suhbat) xodimlarning
ISH KUNLARI yig'indisiga bo'linadi, ya'ni har kimga bir xil KUNLIK norma
tushadi. Oylik ulush esa har kimda har xil bo'ladi — ta'tildagi yoki dam
kuni ko'p xodimga kamroq. Bu eng adolatli usul: 20 kun ishlaydigan xodim
bilan 8 kun ishlaydigani teng oylik reja olmaydi.

TA'TIL/DAM KUNI/YANGI XODIM: ish jadvali (`WorkScheduleWeekly/Override`)
va TASDIQLANGAN sababli kunlar (`ExcusedDay`) hisobga olinadi — payroll
bilan AYNAN bir xil manba, ya'ni «ish kuni» tushunchasi tizim bo'ylab
bitta bo'lib qoladi.

⚠️ AVTOMATIK QO'YILMAYDI. Bu modul faqat TAVSIYA qaytaradi; normani
yozish uchun rahbar alohida tasdiqlaydi (`apply_suggestion`). Reja shuni
ataylab talab qilgan — reja raqami xodimning oylik KPI'siga bevosita
ta'sir qiladi, uni tizim jimgina o'zgartirmasligi kerak.
"""
from __future__ import annotations

import math
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.routers.norms import METRIC_LABELS, can_manage_norms_db, metrics_for
from api.services import payroll as payroll_service
from api.services import target_calc
from db.models import ExcusedDay, ExcusedStatus, Norm, User

# Voronka zanjiridagi qaysi qator qaysi norma metrikasiga tushadi.
# `suhbat` — operatorlar, `tashrif` — menejerlar (lavozim metrikasi hal qiladi).
CHAIN_TO_METRIC = {"talks": "suhbat", "visits": "tashrif"}


def _period_bounds(period: str) -> tuple[date, date]:
    year, month = (int(p) for p in period.split("-"))
    start = date(year, month, 1)
    end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return start, end


async def _working_days(db: AsyncSession, user: User, period: str, excused: set[date]) -> int:
    """Xodimning shu oydagi REJADAGI ish kunlari, tasdiqlangan sababli
    kunlar chiqarib tashlangan holda."""
    days = await payroll_service.month_schedule(db, user, period)
    return sum(1 for d in days if d["is_working"] and d["date"] not in excused)


async def _excused_map(db: AsyncSession, period: str) -> dict[int, set[date]]:
    start, end = _period_bounds(period)
    rows = await db.execute(
        select(ExcusedDay.user_id, ExcusedDay.date).where(
            ExcusedDay.date >= start,
            ExcusedDay.date < end,
            ExcusedDay.status == ExcusedStatus.approved.value,
        )
    )
    out: dict[int, set[date]] = {}
    for user_id, day in rows:
        out.setdefault(user_id, set()).add(day)
    return out


async def _current_norm(db: AsyncSession, user_id: int, metric: str) -> int | None:
    norm = await db.scalar(
        select(Norm)
        .where(Norm.user_id == user_id, Norm.metric_type == metric, Norm.deleted_at.is_(None))
        .order_by(Norm.effective_from.desc(), Norm.created_at.desc())
        .limit(1)
    )
    return norm.value if norm else None


async def suggest(db: AsyncSession, period: str) -> dict:
    """Oylik targetdan har bir xodimga KUNLIK norma tavsiyasi."""
    saved = await target_calc.get_target(db, period)
    if saved is None or not saved.target_contracts:
        return {
            "period": period,
            "ready": False,
            "reason": "Bu oy uchun maqsad qo'yilmagan — avval «nechta uy» ni kiriting",
            "groups": [],
        }

    plan = await target_calc.calculate(
        db, period, saved.target_contracts, saved.assumptions or {}
    )
    chain = {c["key"]: c for c in plan["chain"]}

    users = list(
        await db.scalars(
            select(User).where(User.is_active.is_(True)).order_by(User.full_name)
        )
    )
    excused = await _excused_map(db, period)

    groups = []
    for chain_key, metric in CHAIN_TO_METRIC.items():
        monthly_total = chain.get(chain_key, {}).get("value")
        # Shu metrika lavozimiga BIRIKTIRILGAN xodimlar (norma tizimidagi
        # bilan aynan bir xil qoida — `metrics_for`).
        members = [u for u in users if metric in metrics_for(u)]

        rows = []
        person_days = 0
        for user in members:
            wd = await _working_days(db, user, period, excused.get(user.id, set()))
            person_days += wd
            rows.append({"user": user, "working_days": wd})

        daily = (
            math.ceil(monthly_total / person_days)
            if monthly_total and person_days
            else None
        )

        out_rows = []
        for r in rows:
            user = r["user"]
            current = await _current_norm(db, user.id, metric)
            out_rows.append(
                {
                    "user_id": user.id,
                    "full_name": user.full_name.strip(),
                    "working_days": r["working_days"],
                    "current_daily": current,
                    "suggested_daily": daily if r["working_days"] else 0,
                    "month_total": (daily * r["working_days"]) if daily else 0,
                    "diff": (daily - current) if daily is not None and current is not None else None,
                }
            )

        groups.append(
            {
                "metric": metric,
                "label": METRIC_LABELS.get(metric, metric),
                "monthly_target": monthly_total,
                # Faraz manbai — «taxminiy» bo'lsa rahbar shuni bilib tursin
                "source": chain.get(chain_key, {}).get("source"),
                "person_days": person_days,
                "suggested_daily": daily,
                "employees": out_rows,
                "problem": (
                    "Bu ko'rsatkich hech bir lavozimga biriktirilmagan"
                    if not members
                    else "Ish kuni topilmadi — jadval kiritilmagan"
                    if not person_days
                    else "Maqsaddan bu bosqich hisoblanmadi (faraz yetishmayapti)"
                    if monthly_total is None
                    else None
                ),
            }
        )

    return {
        "period": period,
        "ready": True,
        "target_contracts": saved.target_contracts,
        "baseline_confidence": plan["baseline_confidence"],
        "groups": groups,
    }


async def apply_suggestion(
    db: AsyncSession, period: str, metric: str, actor: User, user_ids: list[int] | None = None
) -> dict:
    """Tavsiyani HAQIQIY normaga aylantiradi (rahbar tasdig'idan keyin).

    Har bir xodim uchun ruxsat alohida tekshiriladi (`can_manage_norms`) —
    ROP o'z jamoasidan tashqariga norma qo'ya olmaydi. Ruxsat yetmagan
    xodimlar jimgina TASHLAB KETILADI va javobda sanaladi: bitta ruxsatsiz
    xodim butun tarqatishni yiqitmasligi kerak."""
    from api.routers.norms import _create_norm  # aylanma importdan qochish

    data = await suggest(db, period)
    if not data["ready"]:
        return {"ok": False, "reason": data["reason"]}

    group = next((g for g in data["groups"] if g["metric"] == metric), None)
    if group is None or group["suggested_daily"] is None:
        return {"ok": False, "reason": "Bu ko'rsatkich uchun tavsiya hisoblanmadi"}

    applied, skipped = 0, 0
    for row in group["employees"]:
        if user_ids is not None and row["user_id"] not in user_ids:
            continue
        if not row["suggested_daily"]:
            continue
        target_user = await db.get(User, row["user_id"])
        if target_user is None or not await can_manage_norms_db(db, actor, target_user):
            skipped += 1
            continue
        await _create_norm(db, actor, target_user, metric, row["suggested_daily"])
        applied += 1

    return {
        "ok": True,
        "metric": metric,
        "applied": applied,
        "skipped_no_permission": skipped,
        "daily": group["suggested_daily"],
    }
