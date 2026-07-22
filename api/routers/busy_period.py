"""Operator/manager'ni vaqtincha "band" (yig'ilish, vazifa va h.k.) deb belgilash —
faqat Boshliq/Dasturchi. Shu vaqt oralig'ida real-vaqtli harakatsizlik nazorati
(`api/services/idle_watch.py`) o'sha odamga ogohlantirish yubormaydi."""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_db, verify_bot_secret
from db.models import OperatorBusyPeriod, Role, User

router = APIRouter(prefix="/busy-periods", tags=["busy-periods"], dependencies=[Depends(verify_bot_secret)])

_MAX_MINUTES = 8 * 60  # xavfsizlik chegarasi — bir martada 8 soatdan ortiq band qilib bo'lmaydi


class SetBusyIn(BaseModel):
    setter_telegram_id: int
    target_user_id: int
    minutes: int
    reason: str | None = None


@router.post("/set")
async def set_busy(payload: SetBusyIn, db: AsyncSession = Depends(get_db)) -> dict:
    setter = await db.scalar(select(User).where(User.telegram_id == payload.setter_telegram_id))
    if not setter or setter.role not in (Role.boss.value, Role.dasturchi.value):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Faqat Boshliq/Dasturchi band vaqt belgilay oladi")

    target = await db.get(User, payload.target_user_id)
    if not target or not target.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Xodim topilmadi")

    minutes = max(1, min(payload.minutes, _MAX_MINUTES))
    now = datetime.utcnow()
    period = OperatorBusyPeriod(
        user_id=target.id,
        set_by=setter.id,
        start_at=now,
        end_at=now + timedelta(minutes=minutes),
        reason=(payload.reason or "").strip()[:255] or None,
    )
    db.add(period)
    await db.commit()
    return {
        "ok": True,
        "target": target.full_name,
        "minutes": minutes,
        "until": period.end_at.isoformat(),
    }


@router.get("/active/{telegram_id}")
async def list_active(telegram_id: int, db: AsyncSession = Depends(get_db)) -> list[dict]:
    """Boshliq/Dasturchi hozir band qilib qo'ygan odamlar ro'yxati (bot ko'rsatish
    uchun ishlatishi mumkin)."""
    actor = await db.scalar(select(User).where(User.telegram_id == telegram_id))
    if not actor or actor.role not in (Role.boss.value, Role.dasturchi.value):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Faqat Boshliq/Dasturchi ko'ra oladi")

    now = datetime.utcnow()
    rows = list(
        await db.scalars(
            select(OperatorBusyPeriod)
            .where(OperatorBusyPeriod.end_at > now)
            .order_by(OperatorBusyPeriod.end_at)
        )
    )
    users = {u.id: u for u in await db.scalars(select(User).where(User.id.in_([r.user_id for r in rows])))}
    return [
        {
            "user": users[r.user_id].full_name if r.user_id in users else "?",
            "until": r.end_at.isoformat(),
            "reason": r.reason,
        }
        for r in rows
    ]
