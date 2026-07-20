"""Sotuv playbook — bot endpointlari (X-Bot-Secret, faqat Boshliq/Dasturchi).

Qurish og'ir AI ishi bo'lgani uchun /build faqat jarayonni ochadi, haqiqiy ish
/tick'da (cron/scheduler har daqiqa) bosqichma-bosqich boradi — knowledge.py
bilan bir xil naqsh. Yozuvlar Boss tasdig'idan keyingina (verified) sotuv AI'ga
(3-bosqich) beriladi."""
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_db, verify_bot_secret
from api.services import sales_playbook as svc
from api.services.knowledge import MANAGER_ROLES
from db.models import AuditLog, PlaybookBuild, PlaybookEntry, User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/playbook", tags=["playbook"], dependencies=[Depends(verify_bot_secret)])


class ActorPayload(BaseModel):
    telegram_id: int


class DecidePayload(BaseModel):
    telegram_id: int
    entry_id: int
    action: str  # approve | delete


async def _require_manager(db: AsyncSession, telegram_id: int) -> User:
    user = await db.scalar(select(User).where(User.telegram_id == telegram_id))
    if not user or not user.is_active or user.role not in MANAGER_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Bu amal faqat Boshliq/Dasturchi uchun")
    return user


def _entry_view(e: PlaybookEntry) -> dict:
    return {
        "id": e.id,
        "kind": e.kind,
        "situation": e.situation,
        "technique": e.technique,
        "phrases": e.phrases or [],
        "status": e.status,
    }


@router.get("/overview/{telegram_id}")
async def overview(telegram_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    await _require_manager(db, telegram_id)
    rows = list(
        await db.execute(
            select(PlaybookEntry.status, func.count()).group_by(PlaybookEntry.status)
        )
    )
    counts = {s: c for s, c in rows}
    build = await svc.active_build(db)
    last_done = await db.scalar(
        select(PlaybookBuild)
        .where(PlaybookBuild.status.in_(["done", "failed"]))
        .order_by(PlaybookBuild.id.desc())
    )
    return {
        "counts": counts,
        "building": (
            {"status": build.status, "label": svc.BUILD_STAGE_LABELS.get(build.status, build.status)}
            if build
            else None
        ),
        "last_build_status": last_done.status if last_done else None,
        "ai_enabled": svc.ai_available(),
    }


@router.post("/build")
async def build(payload: ActorPayload, db: AsyncSession = Depends(get_db)) -> dict:
    actor = await _require_manager(db, payload.telegram_id)
    if await svc.active_build(db) is not None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Playbook allaqachon qurilmoqda — tayyor bo'lgach xabar keladi.",
        )
    if not svc.ai_available():
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "AI o'chiq (.env: AI_ENABLED) — playbook qurish uchun AI kerak.",
        )
    try:
        new_build = await svc.start_build(db, actor)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    db.add(
        AuditLog(
            actor_id=actor.id,
            action="playbook_build_started",
            after={"build_id": new_build.id, "targets": len(new_build.data.get("targets", []))},
        )
    )
    await db.commit()
    return {"build_id": new_build.id, "targets": len(new_build.data.get("targets", []))}


@router.post("/tick")
async def tick(db: AsyncSession = Depends(get_db)) -> dict:
    """Har daqiqa (cron/scheduler): faol build bosqichini davom ettiradi."""
    return await svc.process_build(db)


@router.get("/review-next/{telegram_id}")
async def review_next(
    telegram_id: int, after_id: int = 0, db: AsyncSession = Depends(get_db)
) -> dict:
    await _require_manager(db, telegram_id)
    entry = await db.scalar(
        select(PlaybookEntry)
        .where(PlaybookEntry.status == "unverified", PlaybookEntry.id > after_id)
        .order_by(PlaybookEntry.id)
        .limit(1)
    )
    remaining = await db.scalar(
        select(func.count()).select_from(PlaybookEntry).where(PlaybookEntry.status == "unverified")
    )
    return {"entry": _entry_view(entry) if entry else None, "remaining": remaining or 0}


@router.post("/decide")
async def decide(payload: DecidePayload, db: AsyncSession = Depends(get_db)) -> dict:
    actor = await _require_manager(db, payload.telegram_id)
    entry = await db.get(PlaybookEntry, payload.entry_id)
    if entry is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Yozuv topilmadi")

    if payload.action == "approve":
        entry.status = "verified"
        entry.verified_by = actor.id
        entry.verified_at = datetime.utcnow()
        db.add(
            AuditLog(
                actor_id=actor.id,
                action="playbook_approve",
                after={"id": entry.id, "situation": entry.situation[:200]},
            )
        )
        await db.commit()
        return {"entry": _entry_view(entry)}
    if payload.action == "delete":
        db.add(
            AuditLog(
                actor_id=actor.id,
                action="playbook_delete",
                after={"id": entry.id, "situation": entry.situation[:200]},
            )
        )
        await db.delete(entry)
        await db.commit()
        return {"deleted": True}
    raise HTTPException(status.HTTP_400_BAD_REQUEST, "Noma'lum amal")


@router.get("/export/{telegram_id}")
async def export(telegram_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    await _require_manager(db, telegram_id)
    entries = list(
        await db.scalars(select(PlaybookEntry).order_by(PlaybookEntry.kind, PlaybookEntry.id))
    )
    return {"entries": [_entry_view(e) for e in entries]}
