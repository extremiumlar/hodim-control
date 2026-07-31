"""Push bildirishnomalar — Expo Push API orqali.

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

from datetime import datetime, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.timeutil import TASHKENT_TZ
from db.models import PushSetting, PushToken, User

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"

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


async def should_skip_telegram(db: AsyncSession, user: User, category: str) -> bool:
    """Telegram xabarini o'tkazib yuborish kerakmi.

    Faqat SHAXSIY toifalar uchun va faqat xodimda yaqinda ishlatilgan qurilma
    bo'lsa. Bu yerda ataylab `effective_categories` TEKSHIRILMAYDI: xodim
    push toifasini o'chirib qo'ygan bo'lsa, Telegram yagona kanal bo'lib
    qolishi kerak — aks holda xabar umuman yetib bormaydi.
    """
    if category not in PERSONAL_CATEGORIES:
        return False
    cats = await effective_categories(db, user)
    if not cats.get(category, False):
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
    messages = [
        {
            "to": t.token,
            "title": title,
            "body": body,
            "data": {"category": category, **(data or {})},
            # Tinch soatlarda ovoz/priority pasaytiriladi — xabar yetadi,
            # lekin telefon chalinmaydi.
            "sound": None if quiet else "default",
            "priority": "normal" if quiet else "high",
            "channelId": category,
        }
        for t in tokens
    ]

    responses = await _post_expo(messages)
    if responses is None:
        return 0

    # Expo har xabar uchun alohida status qaytaradi. "DeviceNotRegistered" —
    # ilova o'chirilgan yoki token eskirgan; uni faolsizlantiramiz, aks holda
    # har safar behuda so'rov ketadi.
    sent = 0
    for token_row, item in zip(tokens, responses):
        if item.get("status") == "ok":
            sent += 1
            continue
        if (item.get("details") or {}).get("error") == "DeviceNotRegistered":
            token_row.is_active = False
    await db.commit()
    return sent


async def _post_expo(messages: list[dict]) -> list[dict] | None:
    """Expo push xizmatiga yuborish. Xatolik bo'lsa None — chaqiruvchi oqim
    (masalan vazifa yaratish) push tufayli YIQILMASLIGI kerak."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                EXPO_PUSH_URL,
                json=messages,
                headers={"Accept": "application/json", "Content-Type": "application/json"},
            )
            resp.raise_for_status()
            payload = resp.json()
    except (httpx.HTTPError, ValueError):
        return None

    data = payload.get("data")
    if not isinstance(data, list) or len(data) != len(messages):
        return None
    return data
