"""Sotuvchi AI — bot endpointlari (X-Bot-Secret).

Ro'yxatdan o'tgan har qanday faol xodim foydalanishi mumkin: rahbarlar SINOV
sifatida, operatorlar YORDAMCHI sifatida (mijoz savolini yozadi, AI rasmiy javob
variantini beradi — operator o'zi mijozga yuboradi). Mijoz bilan to'g'ridan-
to'g'ri rejim yo'q."""
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_db, verify_bot_secret
from api.services import sales_ai as svc
from api.services.knowledge import ai_available
from db.models import KnowledgeEntry, KnowledgeStatus, PlaybookEntry, User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sales-ai", tags=["sales-ai"], dependencies=[Depends(verify_bot_secret)])


class AskPayload(BaseModel):
    telegram_id: int
    question: str


async def _require_user(db: AsyncSession, telegram_id: int) -> User:
    user = await db.scalar(select(User).where(User.telegram_id == telegram_id))
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Foydalanuvchi topilmadi")
    return user


@router.get("/overview/{telegram_id}")
async def overview(telegram_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    await _require_user(db, telegram_id)
    kb = await db.scalar(
        select(func.count()).select_from(KnowledgeEntry).where(
            KnowledgeEntry.status == KnowledgeStatus.verified.value
        )
    )
    pb = await db.scalar(
        select(func.count()).select_from(PlaybookEntry).where(PlaybookEntry.status == "verified")
    )
    return {"kb_verified": kb or 0, "pb_verified": pb or 0, "ai_enabled": ai_available()}


@router.post("/ask")
async def ask(payload: AskPayload, db: AsyncSession = Depends(get_db)) -> dict:
    user = await _require_user(db, payload.telegram_id)
    if not (payload.question or "").strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Savol bo'sh")
    return await svc.ask(db, user, payload.question)
