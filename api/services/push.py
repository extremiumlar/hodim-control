"""Push bildirishnomalar — Firebase Cloud Messaging (HTTP v1) orqali.

QAROR (2026-07-31, foydalanuvchi bilan kelishilgan):

1. **Takroriylik.** Ilovadan faol foydalanadigan xodimga SHAXSIY xabarlar
   Telegramga takroran yuborilmaydi (`should_skip_telegram`). Aks holda har
   voqea uchun ikki marta chalinadi va tez bezor qiladi. "Faol" = oxirgi
   `ACTIVE_DEVICE_DAYS` kunda ilova push token'ini tasdiqlagan. Qurilma
   yo'qolsa yoki ilova o'chirilsa bu muddat eskiradi va Telegram O'Z-O'ZIDAN
   qaytadi — ya'ni xabar butunlay yo'qolib qolmaydi.
   JAMOAVIY signallar (issiq lid, digest) bundan MUSTASNO: ular guruh
   chatiga ham ketadi va u yerda tarix sifatida qolishi kerak.

2. **Tinch soatlar.** 22:00-08:00 orasida push OVOZSIZ yuboriladi
   (yetkaziladi, lekin telefon chalinmaydi). Butunlay to'xtatilmaydi —
   ertalab ochganda ko'rinib turishi kerak.

3. **Toifalar.** Standart qiymat ROLGA bog'liq. Xodim o'zgartirsa, faqat
   FARQ `push_settings`ga yoziladi (`db/models.py: PushSetting`) — shuning
   uchun standart keyinchalik o'zgarsa, uni ataylab o'zgartirmagan
   xodimlarga yangi standart qo'llanadi.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import settings
from api.timeutil import TASHKENT_TZ
from db.models import PushSetting, PushToken, User

FCM_SEND_URL = "https://fcm.googleapis.com/v1/projects/{project}/messages:send"
FCM_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"

# Ilova "faol" hisoblanadigan muddat. 7 kun — dam olish kunlari va bir-ikki
# kunlik ta'til push'ni jimgina o'chirib qo'ymasligi uchun yetarlicha uzun.
ACTIVE_DEVICE_DAYS = 7

# Tinch soatlar (mahalliy vaqt): shu oraliqda push ovozsiz.
QUIET_FROM_HOUR = 22
QUIET_TO_HOUR = 8


class Category:
    """Push toifalari. Qiymatlar bazaga yoziladi — O'ZGARTIRMANG."""

    LATE_WARNING = "late_warning"  # kechikish/jarima ogohlantirishi
    TASKS = "tasks"  # yangi vazifa, muddat eslatmasi, bekor qilindi
    DECISIONS = "decisions"  # sababli kun/yuz qarori, bonus, oylik varaqa
    PLAN_REMINDERS = "plan_reminders"  # soatma-soat reja
    APPROVALS = "approvals"  # rahbarga: tasdiq kutilmoqda
    SALES_SIGNALS = "sales_signals"  # issiq lid, harakatsizlik
    DIGESTS = "digests"  # kunlik/haftalik/oylik xulosa


CATEGORY_LABELS: dict[str, str] = {
    Category.LATE_WARNING: "Kechikish ogohlantirishi",
    Category.TASKS: "Vazifalar",
    Category.DECISIONS: "Qaror natijasi",
    Category.PLAN_REMINDERS: "Reja eslatmalari",
    Category.APPROVALS: "Tasdiq kutilmoqda",
    Category.SALES_SIGNALS: "Sotuv signallari",
    Category.DIGESTS: "Kunlik/haftalik xulosa",
}

# Shaxsiy toifalar — ilova faol bo'lsa Telegramga TAKRORLANMAYDI.
# Qolganlari (APPROVALS, SALES_SIGNALS, DIGESTS) guruh chatiga ham ketadi
# yoki tarix sifatida kerak, shuning uchun Telegram doim qoladi.
PERSONAL_CATEGORIES = frozenset(
    {Category.LATE_WARNING, Category.TASKS, Category.DECISIONS, Category.PLAN_REMINDERS}
)

MANAGER_ROLES = frozenset({"hr", "rop", "boss", "dasturchi"})

# Standart holat. Reja eslatmalari ATAYLAB o'chiq — kuniga bir necha marta
# keladi va eng tez charchatadigan toifa. Digestlar ham o'chiq: uzun matn
# push'da o'qilmaydi, Telegram/saytda yaxshiroq.
_DEFAULTS_EMPLOYEE: dict[str, bool] = {
    Category.LATE_WARNING: True,
    Category.TASKS: True,
    Category.DECISIONS: True,
    Category.PLAN_REMINDERS: False,
    Category.APPROVALS: False,
    Category.SALES_SIGNALS: False,
    Category.DIGESTS: False,
}

_DEFAULTS_MANAGER: dict[str, bool] = {
    **_DEFAULTS_EMPLOYEE,
    Category.APPROVALS: True,
    Category.SALES_SIGNALS: True,
}


def default_categories(role: str) -> dict[str, bool]:
    """Rolga qarab standart toifalar. HR'da sotuv signallari kerak emas —
    u lidlar bilan ishlamaydi (bot ham unga BTN_LEAD_STATS ko'rsatmaydi)."""
    base = dict(_DEFAULTS_MANAGER if role in MANAGER_ROLES else _DEFAULTS_EMPLOYEE)
    if role == "hr":
        base[Category.SALES_SIGNALS] = False
    return base


async def effective_categories(db: AsyncSession, user: User) -> dict[str, bool]:
    """Standart + xodimning o'zgartirgan qiymatlari."""
    result = default_categories(user.role)
    rows = await db.scalars(select(PushSetting).where(PushSetting.user_id == user.id))
    for row in rows:
        if row.category in result:  # noma'lum/eskirgan toifa e'tiborsiz qoldiriladi
            result[row.category] = row.enabled
    return result


def _is_quiet_now() -> bool:
    hour = datetime.now(TASHKENT_TZ).hour
    return hour >= QUIET_FROM_HOUR or hour < QUIET_TO_HOUR


async def active_tokens(db: AsyncSession, user_id: int) -> list[PushToken]:
    return list(
        await db.scalars(
            select(PushToken).where(PushToken.user_id == user_id, PushToken.is_active == True)  # noqa: E712
        )
    )


async def should_skip_telegram(db: AsyncSession, user: User, category: str, sent_push: int) -> bool:
    """Telegram xabarini o'tkazib yuborish kerakmi.

    ENG MUHIM shart — `sent_push > 0`, ya'ni push HAQIQATAN yuborilgan
    bo'lishi. Ilgari bu yerda faqat "qurilma bor va toifa yoqiq" tekshirilardi
    va shunda FCM sozlanmagan (yoki kaliti buzilgan) holatda push ham
    ketmasdi, Telegram ham — xabar BUTUNLAY yo'qolardi.

    Qolgan shartlar: faqat SHAXSIY toifalar (jamoaviy signallar guruh
    chatida tarix sifatida qolishi kerak) va qurilma yaqinda ishlatilgan
    bo'lishi (eskirgan token FCM'da hali "ok" qaytarishi mumkin).
    """
    if sent_push <= 0:
        return False
    if category not in PERSONAL_CATEGORIES:
        return False
    cutoff = datetime.utcnow() - timedelta(days=ACTIVE_DEVICE_DAYS)
    token = await db.scalar(
        select(PushToken).where(
            PushToken.user_id == user.id,
            PushToken.is_active == True,  # noqa: E712
            PushToken.last_seen_at >= cutoff,
        )
    )
    return token is not None


async def send_push(
    db: AsyncSession,
    user: User,
    category: str,
    title: str,
    body: str,
    data: dict | None = None,
) -> int:
    """Xodimning barcha faol qurilmalariga push yuboradi. Nechta qurilmaga
    ketgani qaytariladi (0 — token yo'q, toifa o'chiq yoki xatolik)."""
    cats = await effective_categories(db, user)
    if not cats.get(category, False):
        return 0

    tokens = await active_tokens(db, user.id)
    if not tokens:
        return 0

    quiet = _is_quiet_now()
    sent = 0
    for row in tokens:
        status = await _send_one(row.token, category, title, body, data, quiet)
        if status == "ok":
            sent += 1
        elif status == "unregistered":
            # Ilova o'chirilgan yoki token eskirgan — faolsizlantiramiz, aks
            # holda har safar behuda so'rov ketaveradi.
            row.is_active = False
    await db.commit()
    return sent


def _fcm_message(
    token: str, category: str, title: str, body: str, data: dict | None, quiet: bool
) -> dict:
    """FCM HTTP v1 xabari.

    `data` qiymatlari FCM'da FAQAT satr bo'lishi mumkin — son yuborilsa
    so'rov 400 bilan rad etiladi.

    Tinch soatlarda `priority: normal` va kanal ovozsiz: xabar yetkaziladi,
    lekin telefon chalinmaydi.
    """
    payload = {"category": category, **(data or {})}
    return {
        "message": {
            "token": token,
            "notification": {"title": title, "body": body},
            "data": {k: str(v) for k, v in payload.items()},
            "android": {
                "priority": "NORMAL" if quiet else "HIGH",
                "notification": {
                    # Kanal toifa nomi bilan — foydalanuvchi Android
                    # sozlamalarida toifalarni alohida boshqara oladi.
                    "channel_id": f"{category}_quiet" if quiet else category,
                    "default_sound": not quiet,
                },
            },
        }
    }


async def _send_one(
    token: str, category: str, title: str, body: str, data: dict | None, quiet: bool
) -> str:
    """Bitta qurilmaga yuboradi. Qaytaradi: "ok" | "unregistered" | "error".

    Xatolik chaqiruvchi oqimni (masalan vazifa yaratish) YIQITMAYDI — push
    qo'shimcha kanal, u tufayli asosiy amal buzilmasligi kerak.
    """
    access_token = await _access_token()
    if access_token is None:
        return "error"

    url = FCM_SEND_URL.format(project=settings.fcm_project_id)
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                url,
                json=_fcm_message(token, category, title, body, data, quiet),
                headers={"Authorization": f"Bearer {access_token}"},
            )
    except httpx.HTTPError:
        return "error"

    if resp.status_code == 200:
        return "ok"
    # 404 UNREGISTERED / 400 INVALID_ARGUMENT (buzilgan token) — qurilma yo'q.
    if resp.status_code in (403, 404):
        return "unregistered"
    return "error"


# Access token qisqa muddatli (1 soat) — har push uchun qayta olinmasin.
_token_cache: dict[str, float | str] = {"value": "", "expires_at": 0.0}


async def _access_token() -> str | None:
    """FCM uchun OAuth2 access token (service account JWT almashuvi).

    `google.auth`ning tayyor transporti ATAYLAB ishlatilmaydi — u `requests`
    kutubxonasini talab qiladi, bizda esa hamma joyda `httpx` (async). Faqat
    imzolash qismi google-auth'dan olinadi.
    """
    if not settings.fcm_project_id or not settings.fcm_service_account_file:
        return None

    now = time.time()
    cached = _token_cache.get("value")
    if cached and float(_token_cache.get("expires_at", 0)) > now + 60:
        return str(cached)

    try:
        from google.auth import crypt
        from google.auth import jwt as google_jwt

        signer = crypt.RSASigner.from_service_account_file(settings.fcm_service_account_file)
        import json

        with open(settings.fcm_service_account_file, encoding="utf-8") as f:
            client_email = json.load(f)["client_email"]

        assertion = google_jwt.encode(
            signer,
            {
                "iss": client_email,
                "scope": FCM_SCOPE,
                "aud": OAUTH_TOKEN_URL,
                "iat": int(now),
                "exp": int(now) + 3600,
            },
        )
        # `google_jwt.encode` BYTES qaytaradi. Uni to'g'ridan-to'g'ri
        # form-ma'lumotga qo'ysak httpx `b'eyJ...'` ko'rinishida yuboradi va
        # Google 400 "invalid_request" bilan rad etadi (jonli serverda aynan
        # shu xato chiqdi). Satrga o'girish SHART.
        if isinstance(assertion, bytes):
            assertion = assertion.decode("ascii")
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                OAUTH_TOKEN_URL,
                data={
                    "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                    "assertion": assertion,
                },
            )
            resp.raise_for_status()
            payload = resp.json()
    except Exception:
        # Sozlanmagan/noto'g'ri kalit push'ni jim o'chiradi — Telegram ishlayveradi.
        return None

    token = payload.get("access_token")
    if not token:
        return None
    _token_cache["value"] = token
    _token_cache["expires_at"] = now + float(payload.get("expires_in", 3600))
    return token
