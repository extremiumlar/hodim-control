"""Bayram kunlari — HR paneli (yangi TZ 2.9 / S-09).

HR yillik ro'yxatni kiritadi; ro'yxat butun tizimda ish kuni hisobiga
ta'sir qiladi (`api/services/holidays.py` izohiga qarang).

⚠️ O'TGAN DAVRLARGA ATAYIN TEGMAYDI. Bayram qo'shilgach o'tgan oylarning
oyligi qaytadan hisoblanmaydi — tasdiqlangan tarixni buzmaslik uchun.
Kerak bo'lsa HR o'sha davrni qo'lda qayta hisoblatadi.
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user, get_db, require_roles
from db.models import Holiday, HolidayKind, Role, User

router = APIRouter(prefix="/holidays", tags=["holidays"])

_HR = (Role.hr.value, Role.boss.value, Role.dasturchi.value)


class HolidayOut(BaseModel):
    id: int
    date: date
    name: str
    kind: str


class HolidayIn(BaseModel):
    date: date
    name: str = Field(min_length=1, max_length=120)
    kind: str = HolidayKind.state.value


class BulkIn(BaseModel):
    """Yillik ro'yxatni bir marta kiritish — HR uchun asosiy yo'l."""

    items: list[HolidayIn]
    #  `True` bo'lsa allaqachon bor sanalar YANGILANADI, aks holda
    #  o'tkazib yuboriladi. Default `False`: HR ro'yxatni ikkinchi marta
    #  yuborsa qo'lda kiritilgan nomlar ustidan yozilib ketmasin.
    overwrite: bool = False


@router.get("", response_model=list[HolidayOut])
async def list_holidays(
    year: int | None = None,
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[HolidayOut]:
    """Bayramlar ro'yxati. Hamma ko'ra oladi — bu maxfiy ma'lumot emas va
    xodim o'z jadvalida nega dam olish kuni turganini bilishi kerak."""
    q = select(Holiday).order_by(Holiday.date)
    if year is not None:
        q = q.where(Holiday.date >= date(year, 1, 1), Holiday.date <= date(year, 12, 31))
    return [
        HolidayOut(id=h.id, date=h.date, name=h.name, kind=h.kind)
        for h in await db.scalars(q)
    ]


@router.post("", response_model=HolidayOut, status_code=status.HTTP_201_CREATED)
async def add_holiday(
    payload: HolidayIn,
    actor: User = Depends(require_roles(*_HR)),
    db: AsyncSession = Depends(get_db),
) -> HolidayOut:
    if payload.kind not in {k.value for k in HolidayKind}:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Noma'lum tur")
    if await db.scalar(select(Holiday.id).where(Holiday.date == payload.date)):
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"{payload.date} allaqachon bayram sifatida kiritilgan"
        )
    h = Holiday(
        date=payload.date, name=payload.name.strip(), kind=payload.kind, created_by=actor.id
    )
    db.add(h)
    await db.commit()
    await db.refresh(h)
    return HolidayOut(id=h.id, date=h.date, name=h.name, kind=h.kind)


@router.post("/bulk")
async def add_bulk(
    payload: BulkIn,
    actor: User = Depends(require_roles(*_HR)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Yillik ro'yxat. Takrorlangan sanalar `overwrite` ga qarab
    yangilanadi yoki o'tkazib yuboriladi — xato bermaydi, chunki HR
    ro'yxatni bo'lak-bo'lak kiritishi normal holat."""
    mavjud = {
        h.date: h
        for h in await db.scalars(
            select(Holiday).where(Holiday.date.in_([i.date for i in payload.items]))
        )
    }
    qoshildi = yangilandi = otkazildi = 0
    for item in payload.items:
        if item.kind not in {k.value for k in HolidayKind}:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Noma'lum tur: {item.kind}")
        bor = mavjud.get(item.date)
        if bor is not None:
            if payload.overwrite:
                bor.name, bor.kind = item.name.strip(), item.kind
                yangilandi += 1
            else:
                otkazildi += 1
            continue
        db.add(
            Holiday(
                date=item.date, name=item.name.strip(), kind=item.kind, created_by=actor.id
            )
        )
        qoshildi += 1
    await db.commit()
    return {"added": qoshildi, "updated": yangilandi, "skipped": otkazildi}


@router.delete("/{holiday_id}")
async def remove_holiday(
    holiday_id: int,
    _actor: User = Depends(require_roles(*_HR)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    row = await db.get(Holiday, holiday_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Topilmadi")
    await db.execute(delete(Holiday).where(Holiday.id == holiday_id))
    await db.commit()
    return {"ok": True}
