"""Tabrik videolari — bot uchun endpointlar.

Ruxsat: video sozlash faqat Dasturchi / HR / Boshliq. Tekshiruv `telegram_id`
orqali (bot yo'lida JWT yo'q) — `verify_bot_secret` bilan birga, ya'ni so'rov
haqiqiy botdan kelgani ham, uni yuborgan odamning roli ham tekshiriladi.
"""
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_db, require_roles, verify_bot_secret
from api.services import celebration
from db.models import AuditLog, CelebrationKind, Role, User

router = APIRouter(prefix="/celebration", tags=["celebration"])

_ALLOWED_ROLES = {Role.dasturchi.value, Role.hr.value, Role.boss.value}


class CelebrationMediaSet(BaseModel):
    telegram_id: int
    kind: str
    file_id: str
    file_type: str = "video"
    caption: str | None = None


class CelebrationKindAction(BaseModel):
    telegram_id: int
    kind: str


class CelebrationClapIn(BaseModel):
    post_id: int
    telegram_id: int


def _check_kind(kind: str) -> str:
    if kind not in {CelebrationKind.visit.value, CelebrationKind.contract.value}:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Noma'lum tur")
    return kind


async def _actor(db: AsyncSession, telegram_id: int) -> User:
    user = await db.scalar(select(User).where(User.telegram_id == telegram_id))
    if not user or not user.is_active or user.role not in _ALLOWED_ROLES:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Tabrik videosini faqat Dasturchi, HR yoki Boshliq boshqaradi"
        )
    return user


@router.get("/media", dependencies=[Depends(verify_bot_secret)])
async def get_media(telegram_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    await _actor(db, telegram_id)
    return {"items": await celebration.media_overview(db)}


@router.post("/media", dependencies=[Depends(verify_bot_secret)])
async def set_media(payload: CelebrationMediaSet, db: AsyncSession = Depends(get_db)) -> dict:
    actor = await _actor(db, payload.telegram_id)
    kind = _check_kind(payload.kind)
    media = await celebration.set_media(
        db, kind, payload.file_id, payload.file_type, payload.caption, actor.id
    )
    db.add(
        AuditLog(
            actor_id=actor.id,
            action="celebration_media_set",
            after={"kind": kind, "file_type": media.file_type},
        )
    )
    await db.commit()
    return {"ok": True, "kind": kind, "file_type": media.file_type}


@router.post("/media/disable", dependencies=[Depends(verify_bot_secret)])
async def disable_media(payload: CelebrationKindAction, db: AsyncSession = Depends(get_db)) -> dict:
    actor = await _actor(db, payload.telegram_id)
    kind = _check_kind(payload.kind)
    count = await celebration.disable_media(db, kind)
    if count:
        db.add(AuditLog(actor_id=actor.id, action="celebration_media_disabled", after={"kind": kind}))
        await db.commit()
    return {"ok": True, "kind": kind, "disabled": count}


@router.post("/test", dependencies=[Depends(verify_bot_secret)])
async def send_test(payload: CelebrationKindAction, db: AsyncSession = Depends(get_db)) -> dict:
    actor = await _actor(db, payload.telegram_id)
    return await celebration.send_test(db, _check_kind(payload.kind), actor)


@router.post("/clap", dependencies=[Depends(verify_bot_secret)])
async def clap(payload: CelebrationClapIn, db: AsyncSession = Depends(get_db)) -> dict:
    """Guruhdagi HAR KIM bosishi mumkin — rol tekshiruvi ataylab yo'q
    (tabrik ochiq, xodim ham hamkasbini tabriklay olsin)."""
    return await celebration.register_clap(db, payload.post_id, payload.telegram_id)


# ─── Sayt paneli (JWT) ───────────────────────────────────────────────────
# Bot yo'li `telegram_id` + bot siri bilan ishlaydi; sayt yo'lida esa oddiy
# JWT va `require_roles` — ikkalasi ham AYNAN bir xil servisni chaqiradi,
# ya'ni qoidalar (kim o'zgartira oladi, qaysi turlar bor) bir joyda qoladi.
_web_actor = require_roles(Role.dasturchi.value, Role.hr.value, Role.boss.value)


@router.get("/settings")
async def web_settings(
    _actor_user: User = Depends(_web_actor), db: AsyncSession = Depends(get_db)
) -> dict:
    return {"items": await celebration.media_overview(db)}


@router.post("/settings/upload")
async def web_upload(
    kind: str = Form(...),
    caption: str | None = Form(None),
    file: UploadFile = File(...),
    actor: User = Depends(_web_actor),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Saytdan video/GIF yuklash. Fayl serverda SAQLANMAYDI — Telegram'ga
    uzatilib, qaytgan `file_id` bazaga yoziladi."""
    _check_kind(kind)
    content = await file.read()
    res = await celebration.upload_and_set(
        db, kind, content, file.filename or "", file.content_type, (caption or "").strip() or None, actor
    )
    if not res.get("ok"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, res.get("reason") or "Yuklab bo'lmadi")
    db.add(
        AuditLog(
            actor_id=actor.id,
            action="celebration_media_set",
            after={"kind": kind, "file_type": res.get("file_type"), "source": "web"},
        )
    )
    await db.commit()
    return res


@router.post("/settings/disable")
async def web_disable(
    kind: str, actor: User = Depends(_web_actor), db: AsyncSession = Depends(get_db)
) -> dict:
    _check_kind(kind)
    count = await celebration.disable_media(db, kind)
    if count:
        db.add(AuditLog(actor_id=actor.id, action="celebration_media_disabled", after={"kind": kind}))
        await db.commit()
    return {"ok": True, "kind": kind, "disabled": count}


@router.post("/settings/test")
async def web_test(
    kind: str, actor: User = Depends(_web_actor), db: AsyncSession = Depends(get_db)
) -> dict:
    """Sinov — guruhga EMAS, so'ragan rahbarning o'z Telegramiga."""
    res = await celebration.send_test(db, _check_kind(kind), actor)
    if not res.get("ok"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, res.get("reason") or "Yuborib bo'lmadi")
    return res


@router.post("/announce", dependencies=[Depends(verify_bot_secret)])
async def announce(dry_run: bool = False, db: AsyncSession = Depends(get_db)) -> dict:
    """Cron/webhook turtkisi — kutayotgan tabriklarni guruhga yuboradi."""
    return await celebration.announce_pending(db, dry_run=dry_run)
