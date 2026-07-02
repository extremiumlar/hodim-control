from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_db, verify_bot_secret
from api.schemas import MobilografCreate, MobilografOut, MobilografReact
from db.models import AuditLog, MobilografStatus, MobilografVideo, Role, User

router = APIRouter(prefix="/mobilograf-videos", tags=["mobilograf"])


@router.post("", response_model=MobilografOut, dependencies=[Depends(verify_bot_secret)])
async def create_mobilograf_video(payload: MobilografCreate, db: AsyncSession = Depends(get_db)) -> MobilografVideo:
    user = await db.scalar(select(User).where(User.telegram_id == payload.telegram_id))
    if not user or user.role != Role.employee.value:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Faqat xodimlar mobilograf video yubora oladi")

    video = MobilografVideo(
        user_id=user.id,
        telegram_message_id=payload.telegram_message_id,
        group_chat_id=payload.group_chat_id,
        status=MobilografStatus.pending.value,
    )
    db.add(video)
    await db.commit()
    await db.refresh(video)
    return video


@router.post("/react", response_model=MobilografOut, dependencies=[Depends(verify_bot_secret)])
async def react_mobilograf_video(payload: MobilografReact, db: AsyncSession = Depends(get_db)) -> MobilografVideo:
    video = await db.scalar(
        select(MobilografVideo)
        .where(
            MobilografVideo.group_chat_id == payload.group_chat_id,
            MobilografVideo.telegram_message_id == payload.telegram_message_id,
        )
        .order_by(MobilografVideo.sent_at.desc())
    )
    if not video:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Mobilograf video topilmadi")

    reactor = await db.scalar(select(User).where(User.telegram_id == payload.reactor_telegram_id))
    owner = await db.get(User, video.user_id)

    is_authorized = bool(
        reactor
        and owner
        and (reactor.role == Role.boss.value or reactor.id == owner.manager_id)
    )

    if is_authorized and payload.action == "add":
        # Bir nechta ruxsatli reaktordan birinchisi kuchda qoladi.
        if video.status == MobilografStatus.pending.value:
            video.status = MobilografStatus.confirmed.value
            video.confirmed_by = reactor.id
            video.confirmed_at = datetime.utcnow()
            db.add(
                AuditLog(
                    actor_id=reactor.id,
                    action="mobilograf_confirmed",
                    target_user_id=video.user_id,
                    before={"status": MobilografStatus.pending.value},
                    after={"status": MobilografStatus.confirmed.value},
                )
            )
            await db.commit()
            await db.refresh(video)
    elif is_authorized and payload.action == "remove":
        if video.status == MobilografStatus.confirmed.value and video.confirmed_by == reactor.id:
            video.status = MobilografStatus.pending.value
            video.confirmed_by = None
            video.confirmed_at = None
            db.add(
                AuditLog(
                    actor_id=reactor.id,
                    action="mobilograf_unconfirmed",
                    target_user_id=video.user_id,
                    before={"status": MobilografStatus.confirmed.value},
                    after={"status": MobilografStatus.pending.value},
                )
            )
            await db.commit()
            await db.refresh(video)
    elif payload.action not in {"add", "remove"}:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Noto'g'ri amal")

    return video
