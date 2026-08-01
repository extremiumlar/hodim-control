"""Issiq lid (speed-to-lead, 5-bosqich) endpointlari.

`/tick` — scheduler har necha daqiqada chaqiradi: yangi lid aniqlash → operatorga
darhol DM → birinchi qo'ng'iroqni o'lchash → kechikkanini guruhga eskalatsiya.
HOT_LEAD_ENABLED (env) o'chiq bo'lsa no-op; runtime'da boss /ai_sozlama'dan
o'chirsa ham no-op. dry_run — yozmasdan/yubormasdan nima bo'lishini qaytaradi.

`/claim` — bot callback'dan: operator "Qabul qildim" tugmasini bosdi
(aniqlash→qabul reaksiya vaqti qayd etiladi)."""
from datetime import date as date_type, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import settings
from api.deps import get_db, verify_bot_secret
from api.services import hot_lead as hot_lead_service
from api.timeutil import today_local
from db.models import HotLead, Role, User

router = APIRouter(prefix="/hot-lead", tags=["hot-lead"], dependencies=[Depends(verify_bot_secret)])


async def _runtime_enabled(db: AsyncSession) -> bool:
    from api.routers.ai_watch import _get_ai_config  # circular importdan qochish

    cfg = await _get_ai_config(db)
    return cfg.hot_leads_enabled


@router.post("/tick")
async def tick(dry_run: bool = False, db: AsyncSession = Depends(get_db)) -> dict:
    if not settings.hot_lead_enabled and not dry_run:
        return {"disabled": True}
    if not await _runtime_enabled(db) and not dry_run:
        return {"off": True}
    return await hot_lead_service.tick(db, dry_run=dry_run)


@router.get("/accuracy-report")
async def accuracy_report(
    actor_telegram_id: int, day: date_type | None = None, db: AsyncSession = Depends(get_db)
) -> dict:
    """Kunlik issiq-lid aniqlik hisoboti — nazorat uchun: jami/vaqtida/eskalatsiya
    (yolg'on signal avtomatik tuzatilgan/qonuniy yopilgan/hali haqiqiy muammo).

    XAVFSIZLIK: ilgari aktyor umuman tekshirilmasdi — router darajasidagi
    `verify_bot_secret` faqat "so'rov botdan keldimi" degan savolga javob
    beradi, KIM so'rayotganiga emas. Hisobot operatorlarning javob tezligi
    bo'yicha nazorat ma'lumoti, ya'ni rahbar ko'rsatkichi."""
    actor = await db.scalar(select(User).where(User.telegram_id == actor_telegram_id))
    if not actor or not actor.is_active or actor.role not in (
        Role.rop.value, Role.boss.value, Role.dasturchi.value
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Bu amal faqat rahbarlar uchun")
    return await hot_lead_service.daily_accuracy_report(db, day or today_local())


class ClaimIn(BaseModel):
    telegram_id: int
    hot_lead_id: int


@router.post("/claim")
async def claim(payload: ClaimIn, db: AsyncSession = Depends(get_db)) -> dict:
    """Operator issiq lidni qabul qildi. Faqat tayinlangan operator (yoki lid
    egasiz bo'lsa istalgan xodim) qabul qila oladi; qayta bosishda vaqt o'zgarmaydi."""
    user = await db.scalar(select(User).where(User.telegram_id == payload.telegram_id))
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Foydalanuvchi topilmadi")
    lead = await db.get(HotLead, payload.hot_lead_id)
    if not lead:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Lid topilmadi")
    if lead.user_id is not None and lead.user_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Bu lid boshqa operatorga tayinlangan")

    # XAVFSIZLIK: egasiz lid uchun yuqoridagi tekshiruv BUTUNLAY o'tkazib
    # yuboriladi, javob esa mijozning ISMI va TELEFONINI qaytaradi.
    # `hot_lead_id` ketma-ket son va bot `hl:<id>` callback_data'sini
    # foydalanuvchi o'zi yasashi mumkin (Telegram callback_data'ni tugmaga
    # bog'lamaydi) — ya'ni istalgan xodim `hl:1, hl:2, ...` deb mijozlar
    # bazasini yig'ib olardi.
    #
    # Egasiz lid FAQAT guruhga "kim oladi?" deb yuborilgan bo'lsa qabul
    # qilinadi (`notified_at` + `status == notified`). Bunday lidning
    # ma'lumotini guruhdagilar allaqachon ko'rgan, ya'ni oqim buzilmaydi;
    # lekin hali yuborilmagan yoki `baseline` (eski) lidlar yopiq qoladi.
    if lead.user_id is None and (lead.notified_at is None or lead.status != "notified"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Bu lid hozircha qabul qilish uchun ochiq emas")

    if lead.claimed_at is None:
        lead.claimed_at = datetime.utcnow()
        if lead.user_id is None:
            lead.user_id = user.id  # egasiz lidni birinchi qabul qilgan oladi
        if lead.status == "notified":
            lead.status = "claimed"
        await db.commit()

    reaction_sec = int((lead.claimed_at - lead.detected_at).total_seconds())
    return {
        "ok": True,
        "contact": lead.contact_name,
        "phone": lead.phone,
        "reaction_sec": max(reaction_sec, 0),
    }
