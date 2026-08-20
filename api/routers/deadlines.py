"""Muddat eslatmalari — API (yangi TZ 3.5 / S-12).

Ro'yxat HISOBLANADI: qo'lda kiritilgan muddatlar + manbasidan chiqadigan
muddatlar (sinov, hujjat) bitta javobda birlashadi. Tafsilot
`api/services/deadlines.py` izohida.

⚠️ RUXSAT: muddat — xodim haqidagi kadr ma'lumoti (sinov muddati, tibbiy
ko'rik). Kadr hujjatlari bilan bir xil qamrov: HR/Boshliq/Dasturchi.
ROP ko'rmaydi.
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_db, require_roles
from api.services import deadlines as svc
from db.models import DEADLINE_COMPUTED, DEADLINE_KIND_LABELS, Role, User

router = APIRouter(prefix="/deadlines", tags=["deadlines"])

_HR = (Role.hr.value, Role.boss.value, Role.dasturchi.value)


class DeadlineOut(BaseModel):
    key: str
    user_id: int
    user_name: str
    kind: str
    kind_label: str
    due_date: date
    days_left: int
    is_overdue: bool
    responsible_role: str | None
    note: str | None
    row_id: int | None
    #  `True` — sanasi manbasidan hisoblangan, qo'lda tahrirlab bo'lmaydi
    #  (hujjatning o'zini yoki ishga qabul sanasini tuzatish kerak).
    computed: bool


class DeadlineIn(BaseModel):
    user_id: int
    kind: str
    due_date: date
    responsible_role: str | None = None
    note: str | None = Field(default=None, max_length=500)


class ConfigIn(BaseModel):
    probation_days: int = Field(ge=1, le=365)
    remind_days: int = Field(ge=1, le=365)


@router.get("/kinds")
async def kinds(_actor: User = Depends(require_roles(*_HR))) -> list[dict]:
    """Turlar. `computed=True` bo'lganini HR qo'lda kirita olmaydi —
    interfeys ularni ro'yxatdan chiqarib tashlaydi."""
    return [
        {"value": k, "label": v, "computed": k in DEADLINE_COMPUTED}
        for k, v in DEADLINE_KIND_LABELS.items()
    ]


@router.get("", response_model=list[DeadlineOut])
async def list_upcoming(
    days: int | None = None,
    _actor: User = Depends(require_roles(*_HR)),
    db: AsyncSession = Depends(get_db),
) -> list[DeadlineOut]:
    """Yaqinlashayotgan va O'TIB KETGAN muddatlar (pastki chegara yo'q)."""
    return [
        DeadlineOut(
            key=i.key, user_id=i.user_id, user_name=i.user_name, kind=i.kind,
            kind_label=i.kind_label, due_date=i.due_date, days_left=i.days_left,
            is_overdue=i.is_overdue, responsible_role=i.responsible_role,
            note=i.note, row_id=i.row_id, computed=i.source_kind is not None,
        )
        for i in await svc.upcoming(db, days)
    ]


@router.post("", status_code=status.HTTP_201_CREATED)
async def add_deadline(
    payload: DeadlineIn,
    actor: User = Depends(require_roles(*_HR)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if payload.kind not in DEADLINE_KIND_LABELS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Noma'lum tur")
    if payload.kind in DEADLINE_COMPUTED:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"«{DEADLINE_KIND_LABELS[payload.kind]}» muddati hisoblanadi — "
            "qo'lda kiritilmaydi. Manbasini (hujjat yoki ishga qabul sanasi) tuzating.",
        )
    if await db.get(User, payload.user_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Xodim topilmadi")
    row = await svc.create(
        db,
        user_id=payload.user_id,
        kind=payload.kind,
        due_date=payload.due_date,
        responsible_role=payload.responsible_role,
        note=payload.note,
        created_by=actor.id,
    )
    return {"id": row.id, "ok": True}


@router.post("/{deadline_id}/close")
async def close_deadline(
    deadline_id: int,
    cancelled: bool = False,
    _actor: User = Depends(require_roles(*_HR)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Muddatni yopish. Hisoblanadigan bandda ham ishlaydi: uning iz
    qatori yopiladi va band ro'yxatga qaytmaydi."""
    if not await svc.close(db, deadline_id, cancelled=cancelled):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Topilmadi yoki allaqachon yopilgan")
    return {"ok": True}


class CloseByKeyIn(BaseModel):
    key: str
    cancelled: bool = True


@router.post("/close")
async def close_by_key(
    payload: CloseByKeyIn,
    _actor: User = Depends(require_roles(*_HR)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Bandni KALIT bo'yicha yopish — panel shuni ishlatadi.

    Hisoblanadigan bandda (`document:5`) iz qatori hali bo'lmasligi
    mumkin; xizmat uni yopiq holatda o'zi yaratadi."""
    if not await svc.close_by_key(db, payload.key, cancelled=payload.cancelled):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Topilmadi yoki allaqachon yopilgan")
    return {"ok": True}


@router.get("/config")
async def read_config(
    _actor: User = Depends(require_roles(*_HR)), db: AsyncSession = Depends(get_db)
) -> dict:
    cfg = await svc.get_config(db)
    return {"probation_days": cfg.probation_days, "remind_days": cfg.remind_days}


@router.put("/config")
async def write_config(
    payload: ConfigIn,
    _actor: User = Depends(require_roles(*_HR)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    cfg = await svc.get_config(db)
    cfg.probation_days = payload.probation_days
    cfg.remind_days = payload.remind_days
    await db.commit()
    return {"probation_days": cfg.probation_days, "remind_days": cfg.remind_days}
