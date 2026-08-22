"""Tashkiliy tuzilma — API (yangi TZ 3.16 / S-40).

⚠️ SERVER FAQAT MA'LUMOT BERADI (S-40 qabul mezoni). Sxema RASMI
serverda yaratilmaydi: rasm chizish Passenger ishchisini band qilardi
va konkurentlik = 1 bo'lgani uchun butun sayt kutib turardi. Brauzer
`nodes` + `parent_id` dan o'zi chizadi.

⚠️ Marshrut tartibi: so'zli yo'llar `/{position_id}` dan OLDIN
(S-28 da jonli uchragan tuzoq).
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user, get_db, require_roles
from api.services import org as svc
from db.models import Position, Role, User

router = APIRouter(prefix="/org", tags=["org"])

#  TAHRIRLASH — HR/Boshliq/Dasturchi.
_EDIT = (Role.hr.value, Role.boss.value, Role.dasturchi.value)


class ParentIn(BaseModel):
    parent_position_id: int | None = None


class DescriptionIn(BaseModel):
    purpose: str | None = None
    duties: list[str] = []
    rights: list[str] = []
    responsibility: list[str] = []
    requirements: list[str] = []
    effective_from: date | None = None


class ProfileIn(BaseModel):
    mission: str | None = None
    values: list[str] | None = None
    goals: list[str] | None = None


# ─────────────────────────────────────────────────────────────
# SO'ZLI MARSHRUTLAR
# ─────────────────────────────────────────────────────────────


#  Sxemani KO'RISH — rahbarlar (ROP ham). Xodim uchun `/my-place`.
_VIEW_CHART = (
    Role.hr.value,
    Role.boss.value,
    Role.dasturchi.value,
    Role.rop.value,
)


@router.get("/chart")
async def org_chart(
    _actor: User = Depends(require_roles(*_VIEW_CHART)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Sxema ma'lumoti — tugunlar, o'rinlar va bo'shliqlar.

    ⚠️ Rasm QAYTARILMAYDI, faqat ma'lumot. Chizishni brauzer
    qiladi (TZ 3.16).

    ⚠️ RAHBARLAR uchun, xodim uchun EMAS. Javobda `gaps` bor —
    rahbari belgilanmagan xodimlar ro'yxati va shtatdagi bo'sh
    o'rinlar; bu kadr rejalashtirish ma'lumoti. Xodim o'z o'rnini
    `/org/my-place` dan ko'radi.

    Bu chegara S-30 auditida topildi: menyu bo'limi rahbarga
    ochiq edi, endpoint esa hammaga — audit nomuvofiqlikni
    ushladi."""
    return await svc.chart(db)


@router.get("/my-place")
async def my_place(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> dict:
    """«Mening o'rnim»: rahbarim → men → menga bo'ysunadiganlar.

    Mobil ekranda sxema o'rniga shu ko'rsatiladi (S-40 qabul
    mezoni) — kichik ekranda butun daraxtni chizib bo'lmaydi."""
    return await svc.my_place(db, user)


@router.get("/profile")
async def read_profile(
    _user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> dict:
    p = await svc.get_profile(db)
    out = {
        "mission": p.mission,
        "values": p.values or [],
        "goals": p.goals or [],
        "updated_at": p.updated_at,
    }
    await db.commit()  # `get_profile` yangi qator yaratgan bo'lishi mumkin
    return out


@router.put("/profile")
async def write_profile(
    payload: ProfileIn,
    actor: User = Depends(require_roles(*_EDIT)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    p = await svc.update_profile(
        db,
        mission=payload.mission,
        values=payload.values,
        goals=payload.goals,
        actor_id=actor.id,
    )
    out = {"mission": p.mission, "values": p.values or [], "goals": p.goals or []}
    await db.commit()
    return out


# ─────────────────────────────────────────────────────────────
# LAVOZIM (id bilan)
# ─────────────────────────────────────────────────────────────


@router.get("/positions/{position_id}")
async def position_detail(
    position_id: int,
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Lavozim: kim ishlaydi, nechta o'rin, joriy yo'riqnoma."""
    res = await svc.position_detail(db, position_id)
    if res is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Lavozim topilmadi")
    return res


@router.put("/positions/{position_id}/parent")
async def set_parent(
    position_id: int,
    payload: ParentIn,
    _actor: User = Depends(require_roles(*_EDIT)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Ota lavozimni belgilash.

    ⚠️ HALQA to'siladi (`org.assert_no_cycle`) — faqat o'ziga
    bo'ysunish emas, uzun aylana ham."""
    pos = await db.get(Position, position_id)
    if pos is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Lavozim topilmadi")
    try:
        await svc.set_parent(db, position=pos, parent_id=payload.parent_position_id)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
    await db.commit()
    return {"ok": True, "parent_position_id": payload.parent_position_id}


@router.get("/positions/{position_id}/descriptions")
async def list_descriptions(
    position_id: int,
    _actor: User = Depends(require_roles(*_EDIT)),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """BARCHA versiyalar — eskisi ham qoladi va ko'rinadi."""
    return [
        {
            "id": j.id,
            "version": j.version,
            "purpose": j.purpose,
            "duties": j.duties or [],
            "rights": j.rights or [],
            "responsibility": j.responsibility or [],
            "requirements": j.requirements or [],
            "effective_from": j.effective_from,
            "created_at": j.created_at,
        }
        for j in await svc.versions(db, position_id)
    ]


@router.post("/positions/{position_id}/descriptions", status_code=status.HTTP_201_CREATED)
async def add_description(
    position_id: int,
    payload: DescriptionIn,
    actor: User = Depends(require_roles(*_EDIT)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """YANGI versiya qo'shadi.

    ⚠️ TAHRIRLASH ENDPOINTI YO'Q va bo'lmaydi (S-39 qoidasi):
    yo'riqnoma huquqiy hujjat, xodim «tanishdim» degan matn
    o'zgarmasligi kerak."""
    pos = await db.get(Position, position_id)
    if pos is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Lavozim topilmadi")
    j = await svc.add_version(
        db,
        position_id=position_id,
        purpose=payload.purpose,
        duties=payload.duties,
        rights=payload.rights,
        responsibility=payload.responsibility,
        requirements=payload.requirements,
        effective_from=payload.effective_from,
        created_by=actor.id,
    )
    out = {"id": j.id, "version": j.version, "effective_from": j.effective_from}
    await db.commit()
    return out
