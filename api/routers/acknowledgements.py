"""«Tanishdim» — API (yangi TZ / S-20).

Tanishish SO'ROVI bu yerdan berilmaydi: uni manba moduli (e'lon,
yo'riqnoma, instruktaj) o'z obyektini yaratganda `request_ack` orqali
qo'yadi. Bu yerda faqat xodimning ko'rinishi va rahbarning nazorati.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user, get_db, require_roles
from api.services import acknowledgements as svc
from db.models import ACK_OBJECT_LABELS, Role, User

router = APIRouter(prefix="/acks", tags=["acknowledgements"])

_MANAGER = (Role.hr.value, Role.boss.value, Role.dasturchi.value, Role.rop.value)


class PendingOut(BaseModel):
    id: int
    object_type: str
    object_type_label: str
    object_id: int
    version: int
    title: str | None
    link: str | None
    requested_at: datetime


class AckIn(BaseModel):
    object_type: str
    object_id: int
    version: int


class ReaderOut(BaseModel):
    user_id: int
    user_name: str
    version: int
    acknowledged_at: datetime | None


@router.get("/me", response_model=list[PendingOut])
async def my_pending(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[PendingOut]:
    """Men tanishishim kerak bo'lgan bandlar (faqat eng yangi versiya)."""
    return [PendingOut(**i.__dict__) for i in await svc.pending_for(db, user.id)]


@router.post("/me/ack")
async def acknowledge(
    payload: AckIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """«Tanishdim».

    ⚠️ Faqat O'ZIDAN so'ralgan bandni tasdiqlash mumkin. So'ralmagan
    bo'lsa 404: tanishish ro'yxatini manba moduli boshqaradi, xodim
    o'zini o'zi qo'sha olmaydi."""
    if payload.object_type not in ACK_OBJECT_LABELS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Noma'lum obyekt turi")
    row = await svc.mark_ack(
        db,
        user_id=user.id,
        object_type=payload.object_type,
        object_id=payload.object_id,
        version=payload.version,
    )
    if row is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Sizdan bu band bo'yicha tanishish so'ralmagan"
        )
    return {"ok": True, "acknowledged_at": row.acknowledged_at}


@router.get("/object/{object_type}/{object_id}", response_model=list[ReaderOut])
async def readers(
    object_type: str,
    object_id: int,
    version: int | None = None,
    _actor: User = Depends(require_roles(*_MANAGER)),
    db: AsyncSession = Depends(get_db),
) -> list[ReaderOut]:
    """Kim o'qigan, kim o'qimagan. O'QIMAGANLAR TEPADA."""
    if object_type not in ACK_OBJECT_LABELS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Noma'lum obyekt turi")
    return [
        ReaderOut(**r.__dict__)
        for r in await svc.who_read(
            db, object_type=object_type, object_id=object_id, version=version
        )
    ]


@router.get("/object/{object_type}/{object_id}/stats")
async def object_stats(
    object_type: str,
    object_id: int,
    version: int | None = None,
    _actor: User = Depends(require_roles(*_MANAGER)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if object_type not in ACK_OBJECT_LABELS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Noma'lum obyekt turi")
    return await svc.stats(
        db, object_type=object_type, object_id=object_id, version=version
    )


#  Kim tanishgan/tanishmaganini KO'RISH — rahbarlar.
_HR = (Role.hr.value, Role.boss.value, Role.dasturchi.value)


@router.get("/instructions/overview")
async def instructions_overview(
    _actor: User = Depends(require_roles(*_HR)),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """HR paneli: lavozim yo'riqnomalari bo'yicha tanishuv holati.

    ⚠️ FAQAT ENG SO'NGGI VERSIYA. Yo'riqnoma yangilansa ro'yxat
    QAYTADAN ochiladi (TZ 3.16 qabul mezoni) — eski tanishuv
    hisobga olinmaydi, chunki xodim eski matnga rozi bo'lgan.

    ⚠️ `exhausted` — bot uch marta eslatib bo'ldi va endi JIM.
    Aynan shu odamlar bilan HR gaplashishi kerak; ro'yxat shular
    tepada bo'ladigan qilib saralangan.
    """
    from db.models import AckObjectType

    return await svc.overview(db, object_type=AckObjectType.instruction.value)
