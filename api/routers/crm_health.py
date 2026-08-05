"""CRM aloqasi qo'riqchisi endpointlari.

`/tick` — cron/scheduler muntazam chaqiradi: CRM'dan ma'lumot kelmay qolganini
aniqlab guruhga ogohlantiradi (mantiq: `api/services/crm_health.py`).
`/status` — joriy holatni qaytaradi (xabar yubormasdan), diagnostika uchun."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import settings
from api.deps import get_db, verify_bot_secret
from api.services import crm_health

router = APIRouter(prefix="/crm-health", tags=["crm-health"], dependencies=[Depends(verify_bot_secret)])


@router.post("/tick")
async def tick(dry_run: bool = False, db: AsyncSession = Depends(get_db)) -> dict:
    return await crm_health.tick(db, dry_run=dry_run)


@router.get("/status")
async def status(db: AsyncSession = Depends(get_db)) -> dict:
    """Joriy holat — xabar YUBORMAYDI. «CRM ma'lumoti kelayaptimi?» degan
    savolga bir qarashda javob (qo'lda tekshirish/diagnostika uchun)."""
    from datetime import datetime

    last_at = await crm_health.last_data_at(db)
    gap_minutes = None
    if last_at is not None:
        gap_minutes = int((datetime.utcnow() - last_at).total_seconds() // 60)
    return {
        "enabled": settings.crm_health_watchdog_enabled,
        "last_data_at": last_at.isoformat() if last_at else None,
        "gap_minutes": gap_minutes,
        "stale_hours_threshold": settings.crm_health_stale_hours,
        "stale": gap_minutes is not None and gap_minutes > settings.crm_health_stale_hours * 60,
    }
