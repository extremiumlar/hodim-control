from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import settings
from api.deps import get_db
from api.schemas import DevLoginRequest, TokenOut, UserOut
from api.security import create_access_token, verify_telegram_login
from db.models import Role, User

router = APIRouter(prefix="/auth", tags=["auth"])

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


@router.post("/dev-login", response_model=TokenOut)
async def dev_login(payload: DevLoginRequest, db: AsyncSession = Depends(get_db)) -> TokenOut:
    if not settings.debug:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Topilmadi")

    user = await db.scalar(select(User).where(User.telegram_id == payload.telegram_id))
    if not user or not user.is_active or user.role not in SITE_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Saytga kirish uchun ruxsatingiz yo'q")

    return await _issue_token(user)
