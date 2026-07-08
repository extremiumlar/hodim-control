"""Operator AI avto-reja dvigatelini boshqaruvchi endpointlar (2-bosqich).

Barchasi bot-secret bilan himoyalangan (scheduler yoki qo'lda ishga tushirish uchun).
Og'ir ishlar (backfill/snapshot) CRM'ni sekin skanerlaydi — timeout katta qo'yilsin."""
from datetime import date, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_db, verify_bot_secret
from api.services import auto_plan
from api.timeutil import today_local

router = APIRouter(prefix="/auto-plan", tags=["auto-plan"], dependencies=[Depends(verify_bot_secret)])


def _parse_day(day: str | None) -> date:
    return date.fromisoformat(day) if day else today_local()


@router.post("/snapshot")
async def snapshot(day: str | None = None, db: AsyncSession = Depends(get_db)) -> dict:
    """Bitta kun (default bugun) uchun soatlik actual'ni CRM'dan o'qib yozadi."""
    d = _parse_day(day)
    written = await auto_plan.snapshot_hourly_actual(db, d)
    return {"date": d.isoformat(), "rows": written, "crm_ok": written >= 0}


@router.post("/backfill")
async def backfill(days: int = auto_plan.PROFILE_LOOKBACK_DAYS, db: AsyncSession = Depends(get_db)) -> dict:
    """Bootstrap: oxirgi `days` kunni bitta CRM skanerda o'qib `hourly_actual`ga yozadi.
    Uzoq ish (rate-limitga rioya). Kechagi kungacha (bugun `snapshot` orqali)."""
    day_to = today_local() - timedelta(days=1)
    day_from = today_local() - timedelta(days=days)
    written = await auto_plan.backfill_hourly_actual(db, day_from, day_to)
    return {"from": day_from.isoformat(), "to": day_to.isoformat(), "rows": written, "crm_ok": written >= 0}


@router.post("/compute-profiles")
async def compute_profiles(db: AsyncSession = Depends(get_db)) -> dict:
    """Oxirgi ~30 kun actual'dan operator/soat baseline profilini (median) yangilaydi."""
    count = await auto_plan.compute_profiles(db, today_local())
    return {"profiles": count}


@router.post("/build-targets")
async def build_targets(day: str | None = None, db: AsyncSession = Depends(get_db)) -> dict:
    """Berilgan kun (default bugun) uchun soatlik rejani profil+benchmark+stretch'dan tuzadi."""
    d = _parse_day(day)
    count = await auto_plan.build_daily_targets(db, d)
    return {"date": d.isoformat(), "targets": count}
