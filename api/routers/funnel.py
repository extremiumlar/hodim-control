"""Sotuv voronkasi — o'qish endpointlari (1-bosqich).

Ruxsat: KO'RISH — barcha rahbar rollar (`VORONKA_TARIFLAR.md` 3-bo'lim).
Maqsad qo'yish (4-bosqich) alohida ruxsat bilan keyin qo'shiladi.

Hisob YENGIL: hammasi lokal jadvallardan (`lead_events`, `crm_lead_state`,
`hourly_actual`) — CRM'ga so'rov ketmaydi. Shuning uchun keshsiz ham
Passenger'ning yagona ishchisini band qilmaydi.
"""
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_db, require_roles
from api.services import funnel as funnel_service
from db.models import Role, User

router = APIRouter(prefix="/funnel", tags=["funnel"])

_VIEW_ROLES = (Role.hr.value, Role.rop.value, Role.boss.value, Role.dasturchi.value)
_viewer = require_roles(*_VIEW_ROLES)

# Bir so'rovda qamrab olinadigan eng uzun oraliq — tasodifiy «5 yil» so'rovi
# butun jadvalni Pythonda aylanib chiqmasin.
MAX_RANGE_DAYS = 400


def _resolve_range(month: str | None, date_from: date | None, date_to: date | None) -> tuple[date, date]:
    """`month=YYYY-MM` yoki aniq oraliq. Ikkalasi ham berilmasa — joriy oy."""
    if month:
        try:
            year, mon = (int(p) for p in month.split("-"))
            start = date(year, mon, 1)
        except (ValueError, TypeError):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "«month» formati: YYYY-MM")
        end = date(year + 1, 1, 1) if mon == 12 else date(year, mon + 1, 1)
        return start, end - timedelta(days=1)

    if date_from and date_to:
        if date_to < date_from:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "«date_to» «date_from» dan oldin bo'lmasin")
        if (date_to - date_from).days > MAX_RANGE_DAYS:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, f"Oraliq {MAX_RANGE_DAYS} kundan oshmasin"
            )
        return date_from, date_to

    today = date.today()
    start = today.replace(day=1)
    return start, today


@router.get("")
async def get_funnel(
    mode: str = Query("period", pattern="^(period|cohort)$"),
    month: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    _actor: User = Depends(_viewer),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Voronka. `mode=period` — davr kesimi (operativ),
    `mode=cohort` — kogorta (haqiqiy konversiya)."""
    day_from, day_to = _resolve_range(month, date_from, date_to)
    if mode == "cohort":
        data = await funnel_service.cohort_funnel(db, day_from, day_to)
    else:
        data = await funnel_service.period_funnel(db, day_from, day_to)
    data["weakest_link"] = funnel_service.weakest_link(data["rows"])
    return data


@router.get("/channels")
async def get_channels(
    group_by: str = Query("tag", pattern="^(tag|source)$"),
    month: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    _actor: User = Depends(_viewer),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Kanal kesimidagi kogorta — «qaysi reklama sotuv keltirdi».

    `group_by=tag` — CRM teglari (bepul, hamma lidda bor);
    `group_by=source` — attribution kanali (sekin to'ldiriladi, qismi NULL)."""
    day_from, day_to = _resolve_range(month, date_from, date_to)
    return await funnel_service.channel_funnel(db, day_from, day_to, group_by)


@router.get("/months")
async def get_monthly_series(
    months: int = Query(6, ge=2, le=18),
    _actor: User = Depends(_viewer),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Oxirgi N oyning kogorta konversiyasi + o'rtacha va tebranish.

    O'rtachaga FAQAT yetilgan («pishgan») oylar kiradi — yosh kogorta
    konversiyani sun'iy pasaytiradi va rejaga asos bo'la olmaydi."""
    series = await funnel_service.monthly_series(db, months)
    mature = [m for m in series if m["mature"] and m["leads"] > 0]

    def _avg_spread(key: str) -> dict:
        values = [m[key] for m in mature if m[key] is not None]
        if not values:
            return {"avg": None, "min": None, "max": None, "months": 0}
        return {
            "avg": round(sum(values) / len(values), 1),
            "min": min(values),
            "max": max(values),
            "months": len(values),
        }

    return {
        "series": series,
        "summary": {
            "lead_to_visit": _avg_spread("lead_to_visit"),
            "lead_to_contract": _avg_spread("lead_to_contract"),
            "visit_to_contract": _avg_spread("visit_to_contract"),
        },
    }
