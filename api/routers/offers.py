"""Ish takliflari (yangi TZ 3.3 / S-15).

Taklif hozir Word faylida va HR ning yozishmalarida qoladi. «O'tgan oy
falonchiga qancha taklif qilgandik?» degan savolga javob yo'q, kelishilgan
oylik esa ishga qabul qilinganda boshqacha bo'lib chiqadi.

⚠️ TIZIM NOMZODGA HECH NARSA YUBORMAYDI (TZ talabi). Hujjat tayyorlanib
HR ning Telegram'iga boradi; nomzodga uni HR o'zi jo'natadi. Nomzod hali
xodim emas va uning aloqasi bizda bo'lmasligi kerak.

⚠️ `salary` — INTEGER. Matn bo'lsa «12 mln», «12,000,000», «12000000
so'm» aralashib, taqqoslash va yig'ish ishlamasdi.
"""
from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_db, require_roles
from db.models import (
    OFFER_STATUS_LABELS,
    DocumentTemplate,
    Offer,
    OfferStatus,
    Position,
    Role,
    User,
)

router = APIRouter(prefix="/offers", tags=["offers"])

_HR = (Role.hr.value, Role.boss.value, Role.dasturchi.value)

#  Hujjat shabloniga uzatiladigan belgilar. Shablon shu nomlarni
#  ishlatadi ({{fish}}, {{oylik}} ...). Ro'yxat SHU YERDA e'lon qilinadi
#  — HR shablon yozishdan oldin qaysi nomlar borligini bilishi kerak.
OFFER_PLACEHOLDERS: dict[str, str] = {
    "fish": "Nomzod F.I.Sh.",
    "telefon": "Telefon",
    "lavozim": "Lavozim",
    "oylik": "Oylik (raqam bilan)",
    "oylik_sozda": "Oylik (bo'sh joy bilan ajratilgan)",
    "sinov_muddati": "Sinov muddati (oy)",
    "ish_boshlash_sanasi": "Ishga chiqish sanasi",
    "rahbar": "Bo'lajak rahbari",
    "sana": "Bugungi sana",
}


class OfferOut(BaseModel):
    id: int
    candidate_name: str
    phone: str | None
    position_label: str | None
    salary: int
    probation_months: int | None
    start_date: date | None
    manager_id: int | None
    manager_name: str | None
    status: str
    status_label: str
    user_id: int | None
    note: str | None
    created_at: datetime


class OfferIn(BaseModel):
    candidate_name: str = Field(min_length=2, max_length=200)
    phone: str | None = Field(default=None, max_length=32)
    position_id: int | None = None
    position_text: str | None = Field(default=None, max_length=200)
    #  `gt=0` — nol yoki manfiy oylik taklif qilinmaydi; bu odatda
    #  formadagi bo'sh maydonning belgisi.
    salary: int = Field(gt=0)
    probation_months: int | None = Field(default=None, ge=0, le=12)
    start_date: date | None = None
    manager_id: int | None = None
    note: str | None = Field(default=None, max_length=500)


class StatusIn(BaseModel):
    status: str


class GenerateIn(BaseModel):
    template_id: int


def _out(o: Offer, positions: dict[int, str], users: dict[int, str]) -> OfferOut:
    return OfferOut(
        id=o.id,
        candidate_name=o.candidate_name,
        phone=o.phone,
        position_label=(
            positions.get(o.position_id) if o.position_id else o.position_text
        ),
        salary=o.salary,
        probation_months=o.probation_months,
        start_date=o.start_date,
        manager_id=o.manager_id,
        manager_name=users.get(o.manager_id) if o.manager_id else None,
        status=o.status,
        status_label=OFFER_STATUS_LABELS.get(o.status, o.status),
        user_id=o.user_id,
        note=o.note,
        created_at=o.created_at,
    )


async def _lookups(db: AsyncSession) -> tuple[dict[int, str], dict[int, str]]:
    positions = {
        p.id: p.name for p in await db.scalars(select(Position))
    }
    users = {u.id: u.full_name for u in await db.scalars(select(User))}
    return positions, users


@router.get("/placeholders")
async def placeholders(_actor: User = Depends(require_roles(*_HR))) -> list[dict]:
    """Shablonda ishlatiladigan belgilar — HR shablon yozishdan oldin
    ko'radi. Aks holda u o'zicha nom o'ylab topib, hujjat bo'sh chiqardi."""
    return [{"name": k, "label": v} for k, v in OFFER_PLACEHOLDERS.items()]


@router.get("", response_model=list[OfferOut])
async def list_offers(
    q: str | None = None,
    status_filter: str | None = None,
    _actor: User = Depends(require_roles(*_HR)),
    db: AsyncSession = Depends(get_db),
) -> list[OfferOut]:
    """Takliflar ro'yxati. `q` — nomzod ismi yoki telefoni bo'yicha
    qidiruv (TZ: «taklif bazada qoladi, keyin qidiriladi»)."""
    query = select(Offer).order_by(Offer.created_at.desc())
    if status_filter:
        query = query.where(Offer.status == status_filter)
    if q:
        naqsh = f"%{q.strip()}%"
        query = query.where(
            or_(Offer.candidate_name.ilike(naqsh), Offer.phone.ilike(naqsh))
        )
    rows = list(await db.scalars(query))
    positions, users = await _lookups(db)
    return [_out(o, positions, users) for o in rows]


@router.post("", response_model=OfferOut, status_code=status.HTTP_201_CREATED)
async def add_offer(
    payload: OfferIn,
    actor: User = Depends(require_roles(*_HR)),
    db: AsyncSession = Depends(get_db),
) -> OfferOut:
    if not payload.position_id and not (payload.position_text or "").strip():
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Lavozimni tanlang yoki matn bilan yozing",
        )
    if payload.position_id and await db.get(Position, payload.position_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Lavozim topilmadi")
    if payload.manager_id and await db.get(User, payload.manager_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Rahbar topilmadi")

    o = Offer(
        candidate_name=payload.candidate_name.strip(),
        phone=(payload.phone or "").strip() or None,
        position_id=payload.position_id,
        position_text=(payload.position_text or "").strip() or None,
        salary=payload.salary,
        probation_months=payload.probation_months,
        start_date=payload.start_date,
        manager_id=payload.manager_id,
        note=(payload.note or "").strip() or None,
        created_by=actor.id,
    )
    db.add(o)
    await db.commit()
    await db.refresh(o)
    positions, users = await _lookups(db)
    return _out(o, positions, users)


@router.put("/{offer_id}/status", response_model=OfferOut)
async def set_status(
    offer_id: int,
    payload: StatusIn,
    _actor: User = Depends(require_roles(*_HR)),
    db: AsyncSession = Depends(get_db),
) -> OfferOut:
    if payload.status not in OFFER_STATUS_LABELS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Noma'lum holat")
    o = await db.get(Offer, offer_id)
    if o is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Topilmadi")
    o.status = payload.status
    await db.commit()
    await db.refresh(o)
    positions, users = await _lookups(db)
    return _out(o, positions, users)


@router.post("/{offer_id}/generate", status_code=status.HTTP_202_ACCEPTED)
async def generate_document(
    offer_id: int,
    payload: GenerateIn,
    actor: User = Depends(require_roles(*_HR)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Taklif hujjatini NAVBATGA qo'yadi (S-14 mexanizmi).

    Fayl so'rov ichida tayyorlanmaydi: shablon Telegram'dan yuklanadi va
    ZIP qayta yig'iladi — Passenger'da bu butun saytni kutdirib qo'yardi.
    Natija HR ning O'ZIGA boradi; nomzodga tizim hech narsa yubormaydi."""
    from api.services.background_jobs import enqueue

    o = await db.get(Offer, offer_id)
    if o is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Taklif topilmadi")
    tmpl = await db.get(DocumentTemplate, payload.template_id)
    if tmpl is None or not tmpl.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Shablon topilmadi")

    positions, users = await _lookups(db)
    lavozim = positions.get(o.position_id) if o.position_id else o.position_text
    from api.timeutil import today_local

    values = {
        "fish": o.candidate_name,
        "telefon": o.phone or "",
        "lavozim": lavozim or "",
        "oylik": str(o.salary),
        #  Odam o'qishi uchun: 12000000 -> «12 000 000».
        "oylik_sozda": f"{o.salary:,}".replace(",", " "),
        "sinov_muddati": str(o.probation_months) if o.probation_months else "",
        "ish_boshlash_sanasi": o.start_date.isoformat() if o.start_date else "",
        "rahbar": users.get(o.manager_id, "") if o.manager_id else "",
        "sana": today_local().isoformat(),
    }
    yetishmayotgan = [n for n in (tmpl.placeholders or []) if n not in values]

    job = await enqueue(
        db,
        "document_render",
        {
            "template_id": payload.template_id,
            "values": values,
            "filename": f"taklif_{o.candidate_name.replace(' ', '_')}",
        },
        actor.id,
    )
    await db.commit()
    return {"job_id": job.id, "queued": True, "missing": yetishmayotgan}
