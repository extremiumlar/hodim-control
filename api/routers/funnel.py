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

from pydantic import BaseModel

from api.deps import get_db, require_roles
from api.services import ad_spend as ad_spend_service
from api.services import funnel as funnel_service
from api.services import funnel_analysis
from api.services import funnel_operators
from api.services import target_calc
from api.services import target_split
from api.services import target_track
from db.models import AuditLog, Role, User

router = APIRouter(prefix="/funnel", tags=["funnel"])

_VIEW_ROLES = (Role.hr.value, Role.rop.value, Role.boss.value, Role.dasturchi.value)
_viewer = require_roles(*_VIEW_ROLES)

# Xarajat va farazlarni KIM kiritadi — maqsad qo'yuvchilar bilan bir xil
# qamrov (`VORONKA_TARIFLAR.md` 3-bo'lim): Boshliq, Dasturchi, ROP.
_EDIT_ROLES = (Role.boss.value, Role.dasturchi.value, Role.rop.value)
_editor = require_roles(*_EDIT_ROLES)

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


class AdSpendIn(BaseModel):
    period: str
    channel: str
    amount: float
    reach: int | None = None
    note: str | None = None


class AvgProfitIn(BaseModel):
    period: str
    avg_deal_profit: float | None = None


@router.get("/economics")
async def get_economics(
    period: str,
    group_by: str = Query("tag", pattern="^(tag|source)$"),
    _actor: User = Depends(_viewer),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Reklama xarajati + natija: CPL, CPV, CAC, ROMI (3-bosqich)."""
    _resolve_range(period, None, None)  # format tekshiruvi (YYYY-MM)
    return await ad_spend_service.economics(db, period, group_by)


@router.get("/economics/channels")
async def get_known_channels(
    period: str,
    group_by: str = Query("tag", pattern="^(tag|source)$"),
    _actor: User = Depends(_viewer),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Shu oyda HAQIQATAN uchragan kanal nomlari — xarajat kiritish
    formasi shu ro'yxatdan tanlatadi.

    Nega ro'yxat: kanal nomi qo'lda yozilsa («telegram» vs «#telegram»)
    xarajat lidlar bilan bog'lanmay qolardi va CPL jimgina noto'g'ri
    chiqardi."""
    day_from, day_to = _resolve_range(period, None, None)
    data = await funnel_service.channel_funnel(db, day_from, day_to, group_by)
    return {
        "channels": [
            {"channel": r["channel"], "leads": r["leads"]}
            for r in data["rows"]
            if not r["channel"].startswith("(")
        ]
    }


@router.post("/economics/spend")
async def set_spend(
    payload: AdSpendIn, actor: User = Depends(_editor), db: AsyncSession = Depends(get_db)
) -> dict:
    _resolve_range(payload.period, None, None)
    if payload.amount < 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Summa manfiy bo'lmasin")
    row = await ad_spend_service.upsert_spend(
        db, payload.period, payload.channel.strip(), payload.amount,
        payload.reach, (payload.note or "").strip() or None, actor.id,
    )
    db.add(
        AuditLog(
            actor_id=actor.id,
            action="ad_spend_set",
            after={"period": payload.period, "channel": row.channel, "amount": float(row.amount)},
        )
    )
    await db.commit()
    return {"ok": True, "id": row.id}


@router.delete("/economics/spend/{spend_id}")
async def remove_spend(
    spend_id: int, actor: User = Depends(_editor), db: AsyncSession = Depends(get_db)
) -> dict:
    if not await ad_spend_service.delete_spend(db, spend_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Yozuv topilmadi")
    db.add(AuditLog(actor_id=actor.id, action="ad_spend_deleted", before={"id": spend_id}))
    await db.commit()
    return {"ok": True}


@router.post("/economics/avg-profit")
async def set_avg_profit(
    payload: AvgProfitIn, actor: User = Depends(_editor), db: AsyncSession = Depends(get_db)
) -> dict:
    """Bitta shartnomadan o'rtacha foyda — ROMI shu bo'lmasa hisoblanmaydi."""
    _resolve_range(payload.period, None, None)
    if payload.avg_deal_profit is not None and payload.avg_deal_profit < 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Foyda manfiy bo'lmasin")
    await ad_spend_service.set_avg_deal_profit(
        db, payload.period, payload.avg_deal_profit, actor.id
    )
    return {"ok": True}


class TargetIn(BaseModel):
    period: str
    target_contracts: int | None = None
    # Faqat o'zgartirilgan farazlar (bo'shlari o'lchangan qiymatdan olinadi)
    assumptions: dict | None = None


@router.get("/target")
async def get_target(
    period: str,
    target_contracts: int | None = None,
    _actor: User = Depends(_viewer),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Teskari kalkulyator: maqsaddan kerakli lid/suhbat/byudjet (4-bosqich).

    `target_contracts` berilmasa — shu oy uchun SAQLANGAN maqsad olinadi;
    u ham bo'lmasa faqat farazlar qaytariladi (hisob yo'q)."""
    _resolve_range(period, None, None)
    saved = await target_calc.get_target(db, period)
    target = target_contracts if target_contracts is not None else (
        saved.target_contracts if saved else None
    )
    overrides = (saved.assumptions if saved else None) or {}

    if target is None or target <= 0:
        base = await target_calc.baseline(db)
        return {
            "period": period,
            "target_contracts": None,
            "saved_assumptions": overrides,
            "baseline": base,
            "chain": [],
            "hint": "Maqsad kiritilmagan — nechta uy sotmoqchisiz?",
        }

    result = await target_calc.calculate(db, period, target, overrides)
    result["saved_assumptions"] = overrides
    result["saved_target"] = saved.target_contracts if saved else None
    return result


@router.post("/target")
async def save_target(
    payload: TargetIn, actor: User = Depends(_editor), db: AsyncSession = Depends(get_db)
) -> dict:
    """Oylik maqsadni va qo'lda o'zgartirilgan farazlarni saqlaydi."""
    _resolve_range(payload.period, None, None)
    if payload.target_contracts is not None and payload.target_contracts < 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Maqsad manfiy bo'lmasin")
    row = await target_calc.save_target(
        db, payload.period, payload.target_contracts, payload.assumptions, actor.id
    )
    db.add(
        AuditLog(
            actor_id=actor.id,
            action="funnel_target_set",
            after={
                "period": payload.period,
                "target_contracts": row.target_contracts,
                "assumptions": row.assumptions,
            },
        )
    )
    await db.commit()
    return {"ok": True}


class ApplyTargetIn(BaseModel):
    period: str
    metric: str
    # Bo'sh -> guruhdagi HAMMA xodimga; ro'yxat berilsa faqat tanlanganlarga
    user_ids: list[int] | None = None


@router.get("/target/split")
async def get_target_split(
    period: str,
    _actor: User = Depends(_viewer),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Oylik maqsad xodimlarga qanday bo'linadi — TAVSIYA (5-bosqich).

    Hech narsa yozilmaydi: bu faqat «shunday qilsak qanday bo'ladi»
    ko'rinishi. Yozish uchun `POST /funnel/target/split/apply`."""
    _resolve_range(period, None, None)
    return await target_split.suggest(db, period)


@router.post("/target/split/apply")
async def apply_target_split(
    payload: ApplyTargetIn, actor: User = Depends(_editor), db: AsyncSession = Depends(get_db)
) -> dict:
    """Tavsiyani haqiqiy normaga aylantiradi (rahbar tasdig'i)."""
    _resolve_range(payload.period, None, None)
    if payload.metric not in target_split.CHAIN_TO_METRIC.values():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Noma'lum ko'rsatkich")
    result = await target_split.apply_suggestion(
        db, payload.period, payload.metric, actor, payload.user_ids
    )
    if not result.get("ok"):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, result.get("reason") or "Tarqatib bo'lmadi"
        )
    db.add(
        AuditLog(
            actor_id=actor.id,
            action="funnel_target_distributed",
            after={
                "period": payload.period,
                "metric": payload.metric,
                "daily": result["daily"],
                "applied": result["applied"],
            },
        )
    )
    await db.commit()
    return result


@router.get("/target/progress")
async def get_target_progress(
    period: str,
    _actor: User = Depends(_viewer),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Reja / haqiqiy / farq + oy oxiri prognozi (6-bosqich)."""
    _resolve_range(period, None, None)
    return await target_track.progress(db, period)


@router.get("/operators")
async def get_operator_quality(
    month: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    _actor: User = Depends(_viewer),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Operator/menejer kesimida KONVERSIYA — «kim yaxshi yopadi» (7-bosqich).

    Mavjud statistikadan farqi: u mehnat HAJMINI (nechta tashrif), bu esa
    SIFATNI (bergan lidining qanchasi aylandi) ko'rsatadi."""
    day_from, day_to = _resolve_range(month, date_from, date_to)
    return await funnel_operators.operator_quality(db, day_from, day_to)


@router.get("/analysis")
async def get_analysis(
    period: str,
    budget_step: int = Query(20, ge=5, le=200),
    _actor: User = Depends(_viewer),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Bo'g'in tahlili + «agar ...» stsenariylari (7-bosqich, 1 va 2-band)."""
    _resolve_range(period, None, None)
    return {
        "leaks": await funnel_analysis.leak_analysis(db, period),
        "scenarios": await funnel_analysis.scenarios(db, period, budget_step),
    }
