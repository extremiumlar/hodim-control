from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_db, require_roles, verify_bot_secret
from api.routers.norms import METRIC_LABELS, can_manage_norms, metrics_for
from api.schemas import MobilografCreate, MobilografManualCreate, MobilografOut, MobilografReact
from api.timeutil import local_range_utc_naive
from db.models import AuditLog, MobilografSource, MobilografStatus, MobilografVideo, Role, User

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


@router.post("/manual")
async def set_manual_mobilograf_videos(
    payload: MobilografManualCreate,
    actor: User = Depends(require_roles(Role.hr.value, Role.rop.value, Role.boss.value, Role.dasturchi.value)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Kunlik tasdiqlangan videolar sonini qo'lda belgilaydi — guruh reaksiyasi
    oqimi ishlamay qolganda zaxira yo'l. Idempotent "upsert": o'sha kunning eski
    "manual" yozuvlari o'chirilib, `confirmed_count` ta yangi yozuv yaratiladi
    (guruh reaksiyasidan kelgan yozuvlarga tegilmaydi — ular ustiga qo'shiladi)."""
    target = await db.get(User, payload.user_id)
    if not target or target.role != Role.employee.value:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Xodim topilmadi")
    if not can_manage_norms(actor, target):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Bu xodimga video kiritish huquqingiz yo'q")
    if "video" not in metrics_for(target):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Bu xodimning lavozimi uchun '{METRIC_LABELS['video']}' ko'rsatkichi kuzatilmaydi",
        )

    day_start_utc, day_end_utc = local_range_utc_naive(payload.date, payload.date)
    before_count = (
        await db.scalar(
            select(func.count(MobilografVideo.id)).where(
                MobilografVideo.user_id == target.id,
                MobilografVideo.source == MobilografSource.manual.value,
                MobilografVideo.sent_at >= day_start_utc,
                MobilografVideo.sent_at < day_end_utc,
            )
        )
    ) or 0

    await db.execute(
        delete(MobilografVideo).where(
            MobilografVideo.user_id == target.id,
            MobilografVideo.source == MobilografSource.manual.value,
            MobilografVideo.sent_at >= day_start_utc,
            MobilografVideo.sent_at < day_end_utc,
        )
    )

    now = datetime.utcnow()
    for _ in range(payload.confirmed_count):
        db.add(
            MobilografVideo(
                user_id=target.id,
                telegram_message_id=None,
                group_chat_id=None,
                # Kun boshi (Toshkent) — _confirmed_videos_count shu kunga hisoblashi uchun
                sent_at=day_start_utc,
                status=MobilografStatus.confirmed.value,
                source=MobilografSource.manual.value,
                confirmed_by=actor.id,
                confirmed_at=now,
            )
        )

    db.add(
        AuditLog(
            actor_id=actor.id,
            action="mobilograf_manual_set",
            target_user_id=target.id,
            before={"confirmed_count": before_count, "date": payload.date.isoformat()},
            after={"confirmed_count": payload.confirmed_count, "date": payload.date.isoformat()},
        )
    )
    await db.commit()

    return {"user_id": target.id, "date": payload.date.isoformat(), "confirmed_count": payload.confirmed_count}


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
        and (reactor.role in {Role.boss.value, Role.dasturchi.value} or reactor.id == owner.manager_id)
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
