"""Texnika xavfsizligi instruktaji — API (yangi TZ 3.6 / S-48).

⚠️ HAR JAVOBDA QOG'OZ JURNAL OGOHLANTIRISHI. TZ 3.6 qabul mezoni
«qog'oz jurnal o'rnini bosmasligi HUJJATDA yozilgan» deydi — biz
uni kod izohida ham, HR KO'RADIGAN javobda ham qaytaramiz. Faqat
izohda qolsa, uni ekranda ishlaydigan odam hech qachon ko'rmasdi.

⚠️ Marshrut tartibi: so'zli yo'llar `/{id}` dan OLDIN (S-28 tuzog'i).
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user, get_db, require_roles, verify_bot_secret
from api.services import briefings as svc
from db.models import (
    BRIEFING_KIND_LABELS,
    PAPER_JOURNAL_WARNING,
    Role,
    SafetyBriefing,
    User,
)

router = APIRouter(prefix="/briefings", tags=["briefings"])

_BOT_SIR = [Depends(verify_bot_secret)]

#  Instruktaj o'tkazish va jurnalni ko'rish — HR/Boshliq/Dasturchi.
_HR = (Role.hr.value, Role.boss.value, Role.dasturchi.value)


class BriefingIn(BaseModel):
    kind: str
    title: str
    held_on: date
    user_ids: list[int]
    course_id: int | None = None
    repeat_months: int | None = None
    note: str | None = None


class BotAckIn(BaseModel):
    telegram_id: int
    briefing_id: int


@router.get("/kinds")
async def kinds(_user: User = Depends(get_current_user)) -> dict:
    return {
        "kinds": [{"value": k, "label": v} for k, v in BRIEFING_KIND_LABELS.items()],
        "paper_journal_warning": PAPER_JOURNAL_WARNING,
        "default_repeat_months": svc.DEFAULT_REPEAT_MONTHS,
    }


@router.get("/me")
async def my_briefings(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[dict]:
    """Xodimning instruktajlari."""
    return await svc.for_user(db, user.id)


@router.post("/me/{briefing_id}/ack")
async def acknowledge(
    briefing_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await _ack(db, user, briefing_id)


@router.get("/bot/my", dependencies=_BOT_SIR)
async def bot_my_briefings(
    telegram_id: int, db: AsyncSession = Depends(get_db)
) -> list[dict]:
    return await svc.for_user(db, (await _bot_user(db, telegram_id)).id)


@router.post("/bot/ack", dependencies=_BOT_SIR)
async def bot_acknowledge(
    payload: BotAckIn, db: AsyncSession = Depends(get_db)
) -> dict:
    u = await _bot_user(db, payload.telegram_id)
    return await _ack(db, u, payload.briefing_id)


async def _bot_user(db: AsyncSession, telegram_id: int) -> User:
    u = await db.scalar(select(User).where(User.telegram_id == telegram_id))
    if u is None or not u.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Foydalanuvchi topilmadi")
    return u


async def _ack(db: AsyncSession, user: User, briefing_id: int) -> dict:
    """Sayt va bot uchun YAGONA mantiq (loyiha naqshi)."""
    try:
        out = await svc.acknowledge(db, user_id=user.id, briefing_id=briefing_id)
    except ValueError as e:
        #  ⚠️ 404, 403 EMAS: so'ralmagan instruktaj xodim uchun
        #  MAVJUD EMAS — id ning borligini oshkor qilmaymiz
        #  (S-06 qoidasi).
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from e
    await db.commit()
    return out


# ─────────────────────────────────────────────────────────────
# HR — JURNAL
# ─────────────────────────────────────────────────────────────


@router.get("")
async def list_briefings(
    _actor: User = Depends(require_roles(*_HR)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Instruktaj jurnali.

    ⚠️ Javobda `paper_journal_warning` bor va u HR ekranida
    KO'RSATILISHI shart (TZ 3.6 qabul mezoni)."""
    return {
        "paper_journal_warning": PAPER_JOURNAL_WARNING,
        "items": await svc.listing(db),
    }


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_briefing(
    payload: BriefingIn,
    actor: User = Depends(require_roles(*_HR)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        row = await svc.create(
            db,
            kind=payload.kind,
            title=payload.title,
            held_on=payload.held_on,
            user_ids=payload.user_ids,
            conducted_by=actor.id,
            course_id=payload.course_id,
            repeat_months=payload.repeat_months,
            note=payload.note,
            created_by=actor.id,
        )
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
    out = await svc.detail(db, row)
    out["paper_journal_warning"] = PAPER_JOURNAL_WARNING
    await db.commit()
    return out


@router.get("/report")
async def report(
    _actor: User = Depends(require_roles(*_HR)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Hisobot: kim tanishmagan, muddati o'tganlar, kadr auditi.

    ⚠️ Bu yo'l `/{briefing_id}` DAN OLDIN turishi SHART — aks
    holda «report» so'zi id sifatida o'qilib 422 berardi (S-28 da
    jonli uchragan tuzoq).

    ⚠️ OG'IR SO'ROV EMAS: xodimlar o'nlab, instruktajlar yuzlab.
    Ro'yxatlar bir marta o'qiladi va xotirada birlashtiriladi —
    N+1 yo'q."""
    out = await svc.report(db)
    out["paper_journal_warning"] = PAPER_JOURNAL_WARNING
    return out


@router.get("/{briefing_id}")
async def read_briefing(
    briefing_id: int,
    _actor: User = Depends(require_roles(*_HR)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    row = await db.get(SafetyBriefing, briefing_id)
    if row is None or row.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Instruktaj topilmadi")
    out = await svc.detail(db, row)
    out["paper_journal_warning"] = PAPER_JOURNAL_WARNING
    return out
