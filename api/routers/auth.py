import secrets
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import settings
from api.deps import get_db, verify_bot_secret
from api.schemas import (
    DeeplinkClaimRequest,
    DeeplinkPollOut,
    DeeplinkStartOut,
    DevLoginRequest,
    TokenOut,
    UserOut,
)
from api.security import create_access_token, verify_telegram_login
from db.models import LoginToken, Role, User

router = APIRouter(prefix="/auth", tags=["auth"])

# Deep-link login kodi shuncha soniyada muddati o'tadi — sayt oynasi ochiq
# qolib, kimdir eski kodni topib ishlatib qolmasin.
DEEPLINK_TTL_SECONDS = 300

# Barcha faol foydalanuvchilar saytga kira oladi: rahbarlar (boss/rop/hr/dasturchi)
# to'liq boshqaruv panelini, xodimlar (employee) esa faqat o'z davomat (Face ID
# check-in) sahifasini ko'radi. Ruxsat har bir endpointda rol bo'yicha tekshiriladi
# (manager endpointlari employee'ga 403 beradi).
SITE_ROLES = {r.value for r in Role}


async def _issue_token(user: User) -> TokenOut:
    token = create_access_token(user.id, user.role)
    return TokenOut(access_token=token, user=UserOut.model_validate(user))


@router.post("/telegram-login", response_model=TokenOut)
async def telegram_login(data: dict[str, Any], db: AsyncSession = Depends(get_db)) -> TokenOut:
    if not verify_telegram_login(data):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Telegram tekshiruvi muvaffaqiyatsiz")

    telegram_id = int(data["id"])
    user = await db.scalar(select(User).where(User.telegram_id == telegram_id))
    if not user or not user.is_active or user.role not in SITE_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Saytga kirish uchun ruxsatingiz yo'q")

    return await _issue_token(user)


@router.post("/telegram-deeplink/start", response_model=DeeplinkStartOut)
async def telegram_deeplink_start(db: AsyncSession = Depends(get_db)) -> DeeplinkStartOut:
    """Saytga Telegram Login Widget (telefon raqami so'raydigan brauzer oynasi)
    o'rniga bot orqali kirish: bir martalik kod yaratadi, sayt shu kodli deep-link
    (`t.me/<bot>?start=login_<code>`) ni ko'rsatib, /telegram-deeplink/poll bilan
    holatni so'raydi. Bot username sozlanmagan bo'lsa 404 (frontend Login Widget
    bilan bir xil xulq — funksiya "yo'q" ko'rinsin)."""
    if not settings.telegram_login_bot_username:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bot sozlanmagan")

    code = secrets.token_urlsafe(16)
    now = datetime.utcnow()
    db.add(LoginToken(code=code, expires_at=now + timedelta(seconds=DEEPLINK_TTL_SECONDS)))
    await db.commit()

    bot_url = f"https://t.me/{settings.telegram_login_bot_username}?start=login_{code}"
    return DeeplinkStartOut(code=code, bot_url=bot_url, expires_in_seconds=DEEPLINK_TTL_SECONDS)


@router.post("/telegram-deeplink/claim", dependencies=[Depends(verify_bot_secret)])
async def telegram_deeplink_claim(payload: DeeplinkClaimRequest, db: AsyncSession = Depends(get_db)) -> dict:
    """Bot handleri (/start login_<code>) chaqiradi: kodga bosgan odamning
    telegram_id'sini bog'laydi. Haqiqiy JWT bu yerda BERILMAYDI — uni faqat sayt
    /poll orqali, rol/faollik tekshiruvidan o'tib oladi (bot ishonchli kanal
    bo'lsa ham, huquq tekshiruvi bitta joyda — auth qatlamida qolsin)."""
    token = await db.scalar(select(LoginToken).where(LoginToken.code == payload.code))
    if not token or token.consumed or token.expires_at < datetime.utcnow():
        return {"status": "invalid"}
    token.telegram_id = payload.telegram_id
    await db.commit()
    return {"status": "ok"}


@router.get("/telegram-deeplink/poll/{code}", response_model=DeeplinkPollOut)
async def telegram_deeplink_poll(code: str, db: AsyncSession = Depends(get_db)) -> DeeplinkPollOut:
    """Sayt har 2 soniyada shu endpointni so'raydi. telegram_id hali kelmagan
    bo'lsa "pending"; kelgan bo'lsa — shu yerda (faqat shu yerda) foydalanuvchi
    ruxsati tekshirilib JWT beriladi va kod bir martalik ishlatiladi."""
    token = await db.scalar(select(LoginToken).where(LoginToken.code == code))
    if not token:
        return DeeplinkPollOut(status="expired")
    if token.expires_at < datetime.utcnow():
        return DeeplinkPollOut(status="expired")
    if token.consumed:
        return DeeplinkPollOut(status="used")
    if token.telegram_id is None:
        return DeeplinkPollOut(status="pending")

    user = await db.scalar(select(User).where(User.telegram_id == token.telegram_id))
    if not user or not user.is_active or user.role not in SITE_ROLES:
        # Botda /start bosgan, lekin bu Telegram akkaunt saytga kira olmaydi —
        # kod shu bilan yonib bitadi (qayta urinish uchun sayt yangi kod so'raydi).
        token.consumed = True
        await db.commit()
        return DeeplinkPollOut(status="invalid_user")

    token.consumed = True
    await db.commit()
    out = await _issue_token(user)
    return DeeplinkPollOut(status="ready", access_token=out.access_token, user=out.user)


@router.post("/dev-login", response_model=TokenOut)
async def dev_login(payload: DevLoginRequest, db: AsyncSession = Depends(get_db)) -> TokenOut:
    if not settings.debug:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Topilmadi")

    user = await db.scalar(select(User).where(User.telegram_id == payload.telegram_id))
    if not user or not user.is_active or user.role not in SITE_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Saytga kirish uchun ruxsatingiz yo'q")

    return await _issue_token(user)
