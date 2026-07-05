import hmac
from typing import AsyncGenerator

from fastapi import Depends, Header, HTTPException, status
from jwt import PyJWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import settings
from api.security import decode_access_token
from db.base import async_session
from db.models import User


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        yield session


async def get_current_user(
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Kirish talab qilinadi")

    token = authorization.removeprefix("Bearer ").strip()
    try:
        payload = decode_access_token(token)
    except PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token yaroqsiz")

    user = await db.get(User, int(payload["sub"]))
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Foydalanuvchi topilmadi")
    return user


def require_roles(*roles: str):
    async def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Bu amal uchun ruxsat yo'q")
        return user

    return checker


async def verify_bot_secret(x_bot_secret: str | None = Header(default=None)) -> None:
    if not x_bot_secret or not hmac.compare_digest(x_bot_secret, settings.bot_shared_secret):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Bot autentifikatsiyasi muvaffaqiyatsiz")
