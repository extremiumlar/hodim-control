"""Push bildirishnomalar — qurilma ro'yxati va toifalar sozlamasi.

Barcha endpointlar `/me/...` ostida va shaxsni FAQAT tokendan oladi
(`Depends(get_current_user)`) — mijozdan `user_id` qabul qilinmaydi, aks
holda birov boshqasining qurilmasiga push yo'naltira olardi.
"""

from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user, get_db
from api.schemas import PushSettingsOut, PushSettingsUpdate, PushTokenIn
from api.services import push as push_service
from db.models import PushSetting, PushToken, User

router = APIRouter(prefix="/me/push", tags=["push"])


@router.post("/token", response_model=dict)
async def register_push_token(
    payload: PushTokenIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Ilova har ochilganda chaqiradi — token yangi bo'lsa yoziladi, mavjud
    bo'lsa `last_seen_at` yangilanadi.

    `last_seen_at` yangilanishi MUHIM: aynan shu maydon "bu xodim ilovadan
    foydalanadimi" degan savolga javob beradi va shunga qarab Telegram
    xabari takrorlanadimi yoki yo'qmi hal qilinadi (`services/push.py`).
    """
    existing = await db.scalar(select(PushToken).where(PushToken.token == payload.token))
    now = datetime.utcnow()

    if existing is not None:
        # Qurilma boshqa xodimga o'tgan bo'lishi mumkin (bitta telefonni ikki
        # kishi ishlatsa) — egasini yangilaymiz, aks holda push eski egasiga
        # ketaverardi.
        existing.user_id = user.id
        existing.platform = payload.platform
        existing.is_active = True
        existing.last_seen_at = now
    else:
        db.add(
            PushToken(
                user_id=user.id,
                token=payload.token,
                platform=payload.platform,
                is_active=True,
                last_seen_at=now,
                created_at=now,
            )
        )
    await db.commit()
    return {"ok": True}


@router.delete("/token", response_model=dict)
async def unregister_push_token(
    payload: PushTokenIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Chiqishda (logout) chaqiriladi — bu qurilmaga endi push ketmasin.

    Yozuv o'chirilmaydi, faqat faolsizlantiriladi: qaysi qurilma qachon
    uzilganini ko'rish diagnostikada kerak bo'ladi.
    """
    token = await db.scalar(
        select(PushToken).where(PushToken.token == payload.token, PushToken.user_id == user.id)
    )
    if token is not None:
        token.is_active = False
        await db.commit()
    return {"ok": True}


@router.get("/settings", response_model=PushSettingsOut)
async def get_push_settings(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PushSettingsOut:
    """Joriy holat — standart qiymatlar ustiga xodimning o'zgartirishlari."""
    categories = await push_service.effective_categories(db, user)
    return PushSettingsOut(
        categories=categories,
        labels={k: push_service.CATEGORY_LABELS[k] for k in categories},
        quiet_from=push_service.QUIET_FROM_HOUR,
        quiet_to=push_service.QUIET_TO_HOUR,
    )


@router.put("/settings", response_model=PushSettingsOut)
async def update_push_settings(
    payload: PushSettingsUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PushSettingsOut:
    """Toifalarni yoqish/o'chirish.

    Standart bilan bir xil qiymat yozilmaydi, mavjud yozuv esa o'chiriladi —
    shunda standart keyinchalik o'zgarsa, uni ataylab o'zgartirmagan xodimga
    yangi standart qo'llanadi (`db/models.py: PushSetting` izohi).
    """
    defaults = push_service.default_categories(user.role)
    existing = {
        row.category: row
        for row in await db.scalars(select(PushSetting).where(PushSetting.user_id == user.id))
    }

    for category, enabled in payload.categories.items():
        if category not in defaults:
            continue  # noma'lum toifa e'tiborsiz qoldiriladi
        row = existing.get(category)
        if enabled == defaults[category]:
            if row is not None:
                await db.delete(row)
            continue
        if row is not None:
            row.enabled = enabled
            row.updated_at = datetime.utcnow()
        else:
            db.add(
                PushSetting(
                    user_id=user.id,
                    category=category,
                    enabled=enabled,
                    updated_at=datetime.utcnow(),
                )
            )

    await db.commit()
    return await get_push_settings(user=user, db=db)
