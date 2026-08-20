"""Shtat jadvali (yangi TZ 3.20 / S-23).

«Bizda nechta sotuvchi o'rni bor va nechtasi bo'sh?» degan savolga javob
hech qayerda yo'q edi. Ishga olish qarori shunga tayanadi, lekin u har
safar boshdan sanaladi.

⚠️ «BAND» SONI HISOBLANADI, SAQLANMAYDI (TZ qabul mezoni). Faol
xodimlar soni bo'yicha. Qo'lda kiritilsa u darhol eskirardi: xodim
ishdan bo'shaydi, shtat jadvalini yangilash unutiladi va tizim
«hammasi band» deb yolg'on ko'rsatib turaveradi.

⚠️ RUXSAT: xodim UMUMAN ko'rmaydi. ROP faqat O'Z qamrovidagi
lavozimlarni ko'radi — bo'lim tushunchasi (`teams`) amalda bo'sh
bo'lgani uchun qamrov S-06 qatlamidan (`scoped_user_ids`) chiqariladi:
ROP jamoasidagi xodimlar qaysi lavozimlarda bo'lsa, o'sha shtat
birliklarini ko'radi.
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_db, require_roles, scoped_user_ids
from api.timeutil import today_local
from db.models import (
    STAFF_POSITION_STATUS_LABELS,
    Position,
    Role,
    StaffPosition,
    StaffPositionStatus,
    User,
)

router = APIRouter(prefix="/staff", tags=["staff"])

#  Xodim UMUMAN ko'rmaydi. ROP ko'radi, lekin faqat o'z qamrovini.
_VIEW = (Role.hr.value, Role.boss.value, Role.dasturchi.value, Role.rop.value)
#  Tahrirlash — ROP siz: shtat jadvali byudjet hujjati.
_EDIT = (Role.hr.value, Role.boss.value, Role.dasturchi.value)


class StaffOut(BaseModel):
    id: int
    department: str
    position_id: int
    position_name: str
    units: int
    #  ⚠️ Hisoblangan maydonlar — bazada yo'q.
    occupied: int
    vacant: int
    salary_min: int | None
    salary_max: int | None
    status: str
    status_label: str
    effective_from: date
    note: str | None


class StaffIn(BaseModel):
    department: str = Field(min_length=1, max_length=120)
    position_id: int
    units: int = Field(ge=1, le=500)
    salary_min: int | None = Field(default=None, ge=0)
    salary_max: int | None = Field(default=None, ge=0)
    status: str = StaffPositionStatus.open.value
    effective_from: date | None = None
    note: str | None = Field(default=None, max_length=500)


async def _occupied_by_position(db: AsyncSession) -> dict[int, int]:
    """Har lavozimda nechta FAOL xodim bor — bitta so'rovda.

    ⚠️ Faqat `is_active` sanaladi: ishdan bo'shagan xodim o'rinni band
    qilib turmaydi va uning o'rniga odam olish mumkin."""
    rows = await db.scalars(
        select(User).where(User.is_active.is_(True), User.position_id.isnot(None))
    )
    out: dict[int, int] = {}
    for u in rows:
        out[u.position_id] = out.get(u.position_id, 0) + 1
    return out


def _out(sp: StaffPosition, nomlar: dict[int, str], band: dict[int, int]) -> StaffOut:
    #  ⚠️ Bandlik LAVOZIM bo'yicha hisoblanadi. Bir lavozim bir necha
    #  bo'limda bo'lsa, bandlik ular orasida taqsimlanmaydi — bu
    #  soddalashtirish ATAYLAB: aks holda «qaysi bo'limdagi sotuvchi»
    #  degan ma'lumot kerak bo'lardi, u esa `users` da yo'q.
    n = band.get(sp.position_id, 0)
    return StaffOut(
        id=sp.id,
        department=sp.department,
        position_id=sp.position_id,
        position_name=nomlar.get(sp.position_id, "—"),
        units=sp.units,
        occupied=min(n, sp.units),
        vacant=max(0, sp.units - n),
        salary_min=sp.salary_min,
        salary_max=sp.salary_max,
        status=sp.status,
        status_label=STAFF_POSITION_STATUS_LABELS.get(sp.status, sp.status),
        effective_from=sp.effective_from,
        note=sp.note,
    )


async def _visible_position_ids(actor: User, db: AsyncSession) -> set[int] | None:
    """ROP ko'radigan lavozimlar. `None` — cheklovsiz.

    S-06 qatlamidan foydalanadi: ROP jamoasidagi xodimlar qaysi
    lavozimlarda bo'lsa, o'sha shtat birliklari ko'rinadi. Bo'lim
    tushunchasi (`teams`) amalda bo'sh, shuning uchun unga tayanib
    bo'lmasdi."""
    ruxsat = await scoped_user_ids(actor, db)
    if ruxsat is None:
        return None
    rows = await db.scalars(select(User).where(User.id.in_(ruxsat)))
    return {u.position_id for u in rows if u.position_id is not None}


@router.get("", response_model=list[StaffOut])
async def list_staff(
    actor: User = Depends(require_roles(*_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> list[StaffOut]:
    rows = list(
        await db.scalars(
            select(StaffPosition).order_by(
                StaffPosition.department, StaffPosition.effective_from.desc()
            )
        )
    )
    korinadi = await _visible_position_ids(actor, db)
    if korinadi is not None:
        rows = [sp for sp in rows if sp.position_id in korinadi]

    nomlar = {p.id: p.name for p in await db.scalars(select(Position))}
    band = await _occupied_by_position(db)
    return [_out(sp, nomlar, band) for sp in rows]


@router.get("/summary")
async def summary(
    actor: User = Depends(require_roles(*_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Jami shtat / band / bo'sh — va qaysi lavozimlar bo'sh (TZ 2-band).

    Faqat AMALDAGI birliklar sanaladi: muzlatilgan yoki yopilgan o'rin
    «bo'sh» emas, unga odam olish mumkin emas."""
    rows = list(
        await db.scalars(
            select(StaffPosition).where(
                StaffPosition.status == StaffPositionStatus.open.value
            )
        )
    )
    korinadi = await _visible_position_ids(actor, db)
    if korinadi is not None:
        rows = [sp for sp in rows if sp.position_id in korinadi]

    nomlar = {p.id: p.name for p in await db.scalars(select(Position))}
    band = await _occupied_by_position(db)

    jami = sum(sp.units for sp in rows)
    band_jami = sum(min(band.get(sp.position_id, 0), sp.units) for sp in rows)
    bosh = []
    for sp in rows:
        n = max(0, sp.units - band.get(sp.position_id, 0))
        if n:
            bosh.append(
                {
                    "staff_id": sp.id,
                    "department": sp.department,
                    "position_id": sp.position_id,
                    "position_name": nomlar.get(sp.position_id, "—"),
                    "vacant": n,
                    "salary_min": sp.salary_min,
                    "salary_max": sp.salary_max,
                }
            )
    return {
        "total": jami,
        "occupied": band_jami,
        "vacant": jami - band_jami,
        "vacancies": sorted(bosh, key=lambda x: (-x["vacant"], x["position_name"])),
    }


@router.post("", response_model=StaffOut, status_code=status.HTTP_201_CREATED)
async def add_staff(
    payload: StaffIn,
    actor: User = Depends(require_roles(*_EDIT)),
    db: AsyncSession = Depends(get_db),
) -> StaffOut:
    if payload.status not in STAFF_POSITION_STATUS_LABELS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Noma'lum holat")
    if await db.get(Position, payload.position_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Lavozim topilmadi")
    if (
        payload.salary_min is not None
        and payload.salary_max is not None
        and payload.salary_max < payload.salary_min
    ):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Vilkaning yuqori chegarasi pastidan kichik"
        )

    sp = StaffPosition(
        department=payload.department.strip(),
        position_id=payload.position_id,
        units=payload.units,
        salary_min=payload.salary_min,
        salary_max=payload.salary_max,
        status=payload.status,
        effective_from=payload.effective_from or today_local(),
        note=(payload.note or "").strip() or None,
        created_by=actor.id,
    )
    db.add(sp)
    await db.commit()
    await db.refresh(sp)
    nomlar = {p.id: p.name for p in await db.scalars(select(Position))}
    return _out(sp, nomlar, await _occupied_by_position(db))


@router.put("/{staff_id}", response_model=StaffOut)
async def edit_staff(
    staff_id: int,
    payload: StaffIn,
    _actor: User = Depends(require_roles(*_EDIT)),
    db: AsyncSession = Depends(get_db),
) -> StaffOut:
    sp = await db.get(StaffPosition, staff_id)
    if sp is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Topilmadi")
    if payload.status not in STAFF_POSITION_STATUS_LABELS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Noma'lum holat")

    band = (await _occupied_by_position(db)).get(sp.position_id, 0)
    if payload.units < band:
        #  Bandidan kam birlik qo'yish — «minus bo'sh o'rin» degan
        #  ma'nosiz holat. HR avval xodimni ko'chirishi yoki
        #  bo'shatishi kerak.
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Bu lavozimda {band} ta faol xodim bor — birlik sonini undan "
            "kam qilib bo'lmaydi",
        )

    sp.department = payload.department.strip()
    sp.units = payload.units
    sp.salary_min = payload.salary_min
    sp.salary_max = payload.salary_max
    sp.status = payload.status
    sp.note = (payload.note or "").strip() or None
    await db.commit()
    await db.refresh(sp)
    nomlar = {p.id: p.name for p in await db.scalars(select(Position))}
    return _out(sp, nomlar, await _occupied_by_position(db))


@router.delete("/{staff_id}")
async def delete_staff(
    staff_id: int,
    _actor: User = Depends(require_roles(*_EDIT)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Shtat birligini YOPADI (o'chirmaydi).

    Shtat jadvali tarixiy hujjat: «o'tgan yil nechta o'rin bor edi?»
    degan savolga javob berishi kerak."""
    sp = await db.get(StaffPosition, staff_id)
    if sp is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Topilmadi")
    sp.status = StaffPositionStatus.closed.value
    await db.commit()
    return {"ok": True, "status": sp.status}
