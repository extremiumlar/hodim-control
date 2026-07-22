from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_db, verify_bot_secret
from api.schemas import MonitoredGroupOut, MonitoredGroupRemove, MonitoredGroupSet
from db.models import AuditLog, MonitoredGroup, Role, User

router = APIRouter(prefix="/monitored-groups", tags=["monitored-groups"])

# "mobilograf"/"main" — bir vaqtda faqat bitta faol guruh (yangisi ro'yxatga
# olinsa eskisi avtomatik o'chadi — "guruhni o'zgartirish" shunday ishlaydi).
# "stats" — bir nechtasi faol bo'lishi mumkin (hozirgi vergul-ro'yxat naqshi).
EXCLUSIVE_PURPOSES = {"mobilograf", "main"}
ALLOWED_PURPOSES = {"mobilograf", "main", "stats"}


async def _require_dasturchi(db: AsyncSession, telegram_id: int) -> User:
    user = await db.scalar(select(User).where(User.telegram_id == telegram_id))
    if not user or not user.is_active or user.role != Role.dasturchi.value:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Bu amal faqat Dasturchi uchun")
    return user


@router.get("", response_model=list[MonitoredGroupOut], dependencies=[Depends(verify_bot_secret)])
async def list_monitored_groups(purpose: str | None = None, db: AsyncSession = Depends(get_db)) -> list[MonitoredGroup]:
    query = select(MonitoredGroup).where(MonitoredGroup.is_active == True)  # noqa: E712
    if purpose:
        query = query.where(MonitoredGroup.purpose == purpose)
    return list(await db.scalars(query))


@router.post("", response_model=MonitoredGroupOut, dependencies=[Depends(verify_bot_secret)])
async def set_monitored_group(payload: MonitoredGroupSet, db: AsyncSession = Depends(get_db)) -> MonitoredGroup:
    actor = await _require_dasturchi(db, payload.telegram_id)
    if payload.purpose not in ALLOWED_PURPOSES:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"Noma'lum maqsad. Mavjud: {', '.join(sorted(ALLOWED_PURPOSES))}"
        )

    before_active = list(
        await db.scalars(
            select(MonitoredGroup).where(
                MonitoredGroup.purpose == payload.purpose, MonitoredGroup.is_active == True  # noqa: E712
            )
        )
    )

    if payload.purpose in EXCLUSIVE_PURPOSES:
        for row in before_active:
            if row.chat_id != payload.chat_id:
                row.is_active = False

    existing = await db.scalar(
        select(MonitoredGroup).where(
            MonitoredGroup.purpose == payload.purpose, MonitoredGroup.chat_id == payload.chat_id
        )
    )
    if existing:
        existing.is_active = True
        existing.title = payload.title or existing.title
        row = existing
    else:
        row = MonitoredGroup(
            purpose=payload.purpose,
            chat_id=payload.chat_id,
            title=payload.title,
            added_by=actor.id,
        )
        db.add(row)

    db.add(
        AuditLog(
            actor_id=actor.id,
            action="monitored_group_set",
            target_user_id=None,
            before={"purpose": payload.purpose, "chat_ids": [r.chat_id for r in before_active]},
            after={"purpose": payload.purpose, "chat_id": payload.chat_id, "title": payload.title},
        )
    )
    await db.commit()
    await db.refresh(row)
    return row


@router.post("/remove", dependencies=[Depends(verify_bot_secret)])
async def remove_monitored_group(payload: MonitoredGroupRemove, db: AsyncSession = Depends(get_db)) -> dict:
    actor = await _require_dasturchi(db, payload.telegram_id)

    row = await db.scalar(
        select(MonitoredGroup).where(
            MonitoredGroup.purpose == payload.purpose,
            MonitoredGroup.chat_id == payload.chat_id,
            MonitoredGroup.is_active == True,  # noqa: E712
        )
    )
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bu guruh shu maqsad uchun ro'yxatda topilmadi")

    row.is_active = False
    db.add(
        AuditLog(
            actor_id=actor.id,
            action="monitored_group_removed",
            target_user_id=None,
            before={"purpose": payload.purpose, "chat_id": payload.chat_id},
            after=None,
        )
    )
    await db.commit()
    return {"purpose": payload.purpose, "chat_id": payload.chat_id, "removed": True}
