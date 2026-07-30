import secrets
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import settings
from api.deps import get_db, rate_limit, verify_bot_secret
from api.schemas import (
    AppLoginConfirmOut,
    AppLoginConfirmRequest,
    AppLoginPollOut,
    AppLoginPollRequest,
    AppLoginStartOut,
    DevLoginRequest,
    TokenOut,
    UserOut,
)
from api.security import create_access_token, verify_telegram_login
from db.models import AppLoginStatus, AppLoginToken, LoginAttempt, Role, User, UsedTelegramLoginHash

router = APIRouter(prefix="/auth", tags=["auth"])

# Mobil ilova kirishi (deep-link + bir martalik token) — MOBIL_ILOVA_REJASI.md
# 4.1-band. Token shu vaqt ichida tasdiqlanmasa yaroqsiz bo'ladi.
APP_LOGIN_TOKEN_TTL_MINUTES = 5

# Barcha faol foydalanuvchilar saytga kira oladi: rahbarlar (boss/rop/hr/dasturchi)
# to'liq boshqaruv panelini, xodimlar (employee) esa faqat o'z davomat (Face ID
# check-in) sahifasini ko'radi. Ruxsat har bir endpointda rol bo'yicha tekshiriladi
# (manager endpointlari employee'ga 403 beradi).
SITE_ROLES = {r.value for r in Role}


async def _issue_token(user: User) -> TokenOut:
    token = create_access_token(user.id, user.role)
    return TokenOut(access_token=token, user=UserOut.model_validate(user))


@router.post(
    "/telegram-login", response_model=TokenOut,
    dependencies=[Depends(rate_limit("telegram-login", 15, 900))],
)
async def telegram_login(data: dict[str, Any], db: AsyncSession = Depends(get_db)) -> TokenOut:
    if not verify_telegram_login(data):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Telegram tekshiruvi muvaffaqiyatsiz")

    # Replay himoyasi: imzoning o'zi 24 soatlik `auth_date` oynasida amal qiladi
    # (verify_telegram_login) — demak shu oyna ichida ushlab olingan hash bilan
    # qayta so'rov yuborish mumkin edi (masalan brauzer tarixidan eski Login
    # Widget URL'i qayta ochilsa). Har bir hash faqat BIR MARTA qabul qilinadi.
    db.add(UsedTelegramLoginHash(hash=data["hash"]))
    try:
        await db.commit()
    except IntegrityError:
        # Poyga holati: ikkita so'rov bir xil hash bilan deyarli bir vaqtda
        # kelsa — UNIQUE cheklovi ikkinchisini shu yerda ushlaydi.
        await db.rollback()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Bu login havolasi allaqachon ishlatilgan")

    telegram_id = int(data["id"])
    user = await db.scalar(select(User).where(User.telegram_id == telegram_id))
    if not user or not user.is_active or user.role not in SITE_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Saytga kirish uchun ruxsatingiz yo'q")

    return await _issue_token(user)


@router.post(
    "/dev-login", response_model=TokenOut,
    dependencies=[Depends(rate_limit("dev-login", 20, 3600))],
)
async def dev_login(payload: DevLoginRequest, db: AsyncSession = Depends(get_db)) -> TokenOut:
    if not settings.debug:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Topilmadi")

    user = await db.scalar(select(User).where(User.telegram_id == payload.telegram_id))
    if not user or not user.is_active or user.role not in SITE_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Saytga kirish uchun ruxsatingiz yo'q")

    return await _issue_token(user)


@router.post("/bot-token", response_model=TokenOut, dependencies=[Depends(verify_bot_secret)])
async def bot_token(payload: DevLoginRequest, db: AsyncSession = Depends(get_db)) -> TokenOut:
    """Bot orqali Dasturchi buyruqlari (`/norm_set`, `/unlock` va h.k.,
    OYLIK_JARIMA_REJASI.md 11.5-band) uchun ko'prik: bot X-Bot-Secret bilan
    himoyalangan (tashqi hech kim chaqira olmaydi), lekin `/admin/*` va
    boshqa web-darajasidagi endpointlar JWT kutadi — bot uchun bevosita
    kirish yo'q. Shu endpoint TELEGRAM_ID orqali haqiqiy foydalanuvchini
    aniqlab, xuddi shu foydalanuvchi web'dan kirgandagi kabi JWT beradi —
    LEKIN faqat `dasturchi` roli uchun (boshqa rollarga bot orqali to'liq
    web huquqi berilmasin)."""
    user = await db.scalar(select(User).where(User.telegram_id == payload.telegram_id))
    if not user or not user.is_active or user.role != Role.dasturchi.value:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Faqat Dasturchi uchun")
    return await _issue_token(user)


@router.post("/app-login/start", response_model=AppLoginStartOut)
async def app_login_start(db: AsyncSession = Depends(get_db)) -> AppLoginStartOut:
    """Mobil ilova ekrani ochilganda chaqiradi: yangi bir martalik token yaratadi
    va foydalanuvchi botga o'tishi uchun deep-link qaytaradi (4.1-band)."""
    token = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(minutes=APP_LOGIN_TOKEN_TTL_MINUTES)
    db.add(AppLoginToken(token=token, expires_at=expires_at))
    await db.commit()

    bot_username = settings.telegram_login_bot_username
    deep_link = f"https://t.me/{bot_username}?start=applogin_{token}"
    return AppLoginStartOut(login_token=token, deep_link=deep_link, expires_at=expires_at)


@router.post(
    "/app-login/confirm", response_model=AppLoginConfirmOut, dependencies=[Depends(verify_bot_secret)]
)
async def app_login_confirm(
    payload: AppLoginConfirmRequest, db: AsyncSession = Depends(get_db)
) -> AppLoginConfirmOut:
    """Bot `/start applogin_<token>` qabul qilib, foydalanuvchi tasdiqlagach
    chaqiradi. Faqat bot chaqira oladi (X-Bot-Secret) — ilova to'g'ridan-to'g'ri
    `telegram_id` yubora olmaydi, aks holda boshqa birovning hisobiga kirish
    so'ralishi mumkin edi."""
    row = await db.scalar(select(AppLoginToken).where(AppLoginToken.token == payload.login_token))
    if not row or row.status != AppLoginStatus.pending.value or row.expires_at < datetime.utcnow():
        return AppLoginConfirmOut(status="invalid")

    user = await db.scalar(select(User).where(User.telegram_id == payload.telegram_id))
    if not user or not user.is_active or user.role not in SITE_ROLES:
        return AppLoginConfirmOut(status="no_account")

    row.telegram_id = payload.telegram_id
    row.status = AppLoginStatus.confirmed.value
    row.confirmed_at = datetime.utcnow()
    await db.commit()
    return AppLoginConfirmOut(status="ok")


@router.post("/app-login/poll", response_model=AppLoginPollOut)
async def app_login_poll(
    payload: AppLoginPollRequest, db: AsyncSession = Depends(get_db)
) -> AppLoginPollOut:
    """Ilova login ekranida bir necha soniyada bir chaqirib turadi. Token
    tasdiqlangan zahoti JWT beriladi va token BIR MARTALIK sifatida
    iste'mol qilinadi (qayta pollansa "expired" qaytadi)."""
    row = await db.scalar(select(AppLoginToken).where(AppLoginToken.token == payload.login_token))
    if not row or row.expires_at < datetime.utcnow() or row.status == AppLoginStatus.used.value:
        return AppLoginPollOut(status="expired")

    if row.status == AppLoginStatus.pending.value:
        return AppLoginPollOut(status="pending")

    user = await db.scalar(select(User).where(User.telegram_id == row.telegram_id))
    if not user or not user.is_active or user.role not in SITE_ROLES:
        return AppLoginPollOut(status="expired")

    row.status = AppLoginStatus.used.value
    row.used_at = datetime.utcnow()
    await db.commit()
    return AppLoginPollOut(status="confirmed", token=await _issue_token(user))


@router.post("/login-security-cleanup", dependencies=[Depends(verify_bot_secret)])
async def login_security_cleanup(db: AsyncSession = Depends(get_db)) -> dict:
    """Scheduler tick (Telegram login xavfsizlik arxitekturasi): replay-himoya
    hash'lari va rate-limit urinish yozuvlarini tozalaydi — ikkalasi ham vaqt
    o'tgach umuman kerak bo'lmaydi, jadval cheksiz o'sib ketmasin.

    Hash'lar 25 soatdan (24 soatlik `auth_date` oynasidan xavfsizlik zahirasi
    bilan) oshganda o'chiriladi — imzo o'zi shu vaqtda allaqachon yaroqsiz
    bo'lib qoladi. Urinish yozuvlari 1 soatdan oshganda — eng uzun oyna
    (dev-login, 3600s) shundan qisqa."""
    hash_cutoff = datetime.utcnow() - timedelta(hours=25)
    attempt_cutoff = datetime.utcnow() - timedelta(hours=1)

    hash_result = await db.execute(delete(UsedTelegramLoginHash).where(UsedTelegramLoginHash.consumed_at < hash_cutoff))
    attempt_result = await db.execute(delete(LoginAttempt).where(LoginAttempt.created_at < attempt_cutoff))
    await db.commit()

    return {"deleted_hashes": hash_result.rowcount, "deleted_attempts": attempt_result.rowcount}
