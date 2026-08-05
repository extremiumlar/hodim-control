"""Tizim sog'ligi qo'riqchisi endpointlari.

`/tick` — cron/scheduler muntazam chaqiradi: jimgina ishlamay qolgan qismlarni
(CRM aloqasi, zaxira nusxa, davomat) aniqlab guruhga ogohlantiradi.
Mantiq: `api/services/system_health.py`.

`/status` — joriy holat, xabar YUBORMASDAN (qo'lda tekshirish/diagnostika)."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_db, verify_bot_secret
from api.services import system_health

router = APIRouter(
    prefix="/system-health", tags=["system-health"], dependencies=[Depends(verify_bot_secret)]
)


@router.post("/tick")
async def tick(dry_run: bool = False, db: AsyncSession = Depends(get_db)) -> dict:
    return await system_health.tick(db, dry_run=dry_run)


@router.get("/status")
async def status(db: AsyncSession = Depends(get_db)) -> dict:
    """Barcha tekshiruvlar holati — hech narsa yubormaydi/yozmaydi."""
    return await system_health.tick(db, dry_run=True)
