import hmac
from datetime import datetime, timedelta
from typing import AsyncGenerator

from fastapi import Depends, Header, HTTPException, Request, status
from jwt import PyJWTError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import settings
from api.security import decode_access_token
from db.base import async_session
from db.models import LoginAttempt, Role, User


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


def is_superadmin(user: User) -> bool:
    """Bosqich 3.5 (Dasturchi rejimi) — YAGONA DARVOZA. Har bir `can_manage_*`/
    matritsa funksiyasi eng boshida shuni tekshiradi va `True` bo'lsa darhol
    ruxsat beradi — cheklov mantig'i tarqoq bo'lib ketmasligi uchun."""
    return user.role == Role.dasturchi.value


async def require_dasturchi(user: User = Depends(get_current_user)) -> User:
    """`/admin/*` — cheklovsiz boshqaruv endpointlari FAQAT Dasturchi uchun."""
    if not is_superadmin(user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Bu amal faqat Dasturchi uchun")
    return user


async def verify_bot_secret(x_bot_secret: str | None = Header(default=None)) -> None:
    if not x_bot_secret or not hmac.compare_digest(x_bot_secret, settings.bot_shared_secret):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Bot autentifikatsiyasi muvaffaqiyatsiz")


def rate_limit(endpoint: str, max_attempts: int, window_seconds: int):
    """So'rov chastotasini DB asosida cheklaydigan sliding-window dependency
    fabrikasi. Bu yerda himoyalanadigan endpointlar parol SO'RAMAYDI (Telegram
    Login Widget imzosi yoki tasodifiy bir martalik token) — demak bu
    BRUTE-FORCE HIMOYASI EMAS, faqat DoS/resurs himoyasi (xato konfiguratsiya
    yoki niyatli bombalash API'ni/bazani band qilib qo'ymasin).

    IP `X-Forwarded-For` headeridan olinadi (birinchi qiymat), topilmasa
    `request.client.host`ga tushadi. DIQQAT: production'da (cPanel/nginx) bu
    header TO'G'RI uzatilishi SHART — aks holda barcha so'rovlar bitta
    manzildan kelayotgandek ko'rinib, bitta faol foydalanuvchi hammani
    bloklab qo'yishi mumkin."""

    async def checker(request: Request, db: AsyncSession = Depends(get_db)) -> None:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            identifier = forwarded.split(",")[0].strip()
        else:
            identifier = request.client.host if request.client else "unknown"

        window_start = datetime.utcnow() - timedelta(seconds=window_seconds)
        count = await db.scalar(
            select(func.count()).select_from(LoginAttempt).where(
                LoginAttempt.endpoint == endpoint,
                LoginAttempt.identifier == identifier,
                LoginAttempt.created_at >= window_start,
            )
        )
        if count and count >= max_attempts:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS, "Juda ko'p urinish — birozdan keyin qayta urinib ko'ring"
            )

        db.add(LoginAttempt(endpoint=endpoint, identifier=identifier))
        await db.commit()

    return checker
