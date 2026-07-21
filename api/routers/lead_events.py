"""Diff-engine endpointlari (`api/services/lead_diff.py`) — CRM lidlarining
haqiqiy holat o'zgarishlarini kuzatib, kunlik statistikani (guruh digesti)
"bugun tegilgan (istalgan tahrir)" taxminidan "haqiqatan bosqich/mas'ul
o'zgardi" voqeasiga o'tkazadi.

`/diff-tick` — scheduler tez-tez (bir necha daqiqada) chaqiradi: faqat so'nggi
CRM_UYSOT_LEAD_DIFF_LOOKBACK_DAYS kunda yaratilgan lidlar (tez skan).
`/reconcile` — kamdan-kam (tunda bir marta): BUTUN bazani skanerlaydi (sekin) —
lookback oynasidan tashqarida qolgan eski-lekin-qayta-faollashgan lidlarni
ushlab qoladigan xavfsizlik to'ri."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_db, verify_bot_secret
from api.services import lead_diff

router = APIRouter(prefix="/lead-events", tags=["lead-events"], dependencies=[Depends(verify_bot_secret)])


@router.post("/diff-tick")
async def diff_tick(dry_run: bool = False, db: AsyncSession = Depends(get_db)) -> dict:
    return await lead_diff.diff_tick(db, full=False, dry_run=dry_run)


@router.post("/reconcile")
async def reconcile(dry_run: bool = False, db: AsyncSession = Depends(get_db)) -> dict:
    return await lead_diff.diff_tick(db, full=True, dry_run=dry_run)
