"""Real-vaqtli harakatsizlik nazorati (4-band) endpointi — `/tick` scheduler
tomonidan tez-tez (5-10 daqiqada) chaqiriladi."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import settings
from api.deps import get_db, verify_bot_secret
from api.services import idle_watch

router = APIRouter(prefix="/idle-watch", tags=["idle-watch"], dependencies=[Depends(verify_bot_secret)])


@router.post("/tick")
async def tick(dry_run: bool = False, db: AsyncSession = Depends(get_db)) -> dict:
    if not settings.ai_enabled and not dry_run:
        return {"disabled": True}

    from api.routers.ai_watch import _get_ai_config  # circular importdan qochish

    cfg = await _get_ai_config(db)
    if not cfg.idle_alerts_enabled and not dry_run:
        return {"idle_alerts_disabled": True}

    return await idle_watch.evaluate_and_alert(db, dry_run=dry_run)
