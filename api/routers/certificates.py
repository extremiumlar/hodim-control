"""Berilgan ma'lumotnomalar arxivi (yangi TZ 3.9 / S-17).

TZ: «arxivda kimga, qachon, qaysi maqsadda tarixi qoladi». Amalda bu
savol tez-tez chiqadi — «bu odamga shu yil nechta ma'lumotnoma berdik?»,
«bankka bergani qaysi raqamda edi?».

Ma'lumotnomaning O'ZI bu yerdan berilmaydi: u ariza tasdiqlanganda
avtomatik chiqadi (`api/routers/requests.py::_apply_certificate`).
Bu yerda faqat arxiv va HR ning qo'lda berish yo'li (arizasiz holat —
xodim og'zaki so'ragan).
"""
from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_db, require_roles
from api.services import certificates as svc
from db.models import (
    CERTIFICATE_PURPOSE_LABELS,
    Certificate,
    CertificatePurpose,
    Role,
    User,
)

router = APIRouter(prefix="/certificates", tags=["certificates"])

_HR = (Role.hr.value, Role.boss.value, Role.dasturchi.value)


class CertificateOut(BaseModel):
    id: int
    user_id: int
    user_name: str
    purpose: str
    purpose_label: str
    number: str
    include_salary: bool
    #  ⚠️ Summa QAYTARILMAYDI. Arxivda «oylik yozilganmi?» degan BAYROQ
    #  yetarli; raqamning o'zi hujjatda va u maxfiy.
    issued_at: date
    request_id: int | None
    document_id: int | None
    created_at: datetime


class IssueIn(BaseModel):
    user_id: int
    purpose: str
    include_salary: bool = False


@router.get("/purposes")
async def purposes(_actor: User = Depends(require_roles(*_HR))) -> list[dict]:
    return [{"value": k, "label": v} for k, v in CERTIFICATE_PURPOSE_LABELS.items()]


@router.get("/placeholders")
async def placeholders(_actor: User = Depends(require_roles(*_HR))) -> list[dict]:
    """Shablonda ishlatiladigan belgilar — HR shablon yozishdan oldin
    ko'radi (S-15 dagi bilan bir xil naqsh)."""
    return [{"name": k, "label": v} for k, v in svc.CERTIFICATE_PLACEHOLDERS.items()]


@router.get("", response_model=list[CertificateOut])
async def list_certificates(
    user_id: int | None = None,
    year: int | None = None,
    _actor: User = Depends(require_roles(*_HR)),
    db: AsyncSession = Depends(get_db),
) -> list[CertificateOut]:
    q = select(Certificate).order_by(Certificate.issued_at.desc(), Certificate.id.desc())
    if user_id:
        q = q.where(Certificate.user_id == user_id)
    if year:
        q = q.where(
            Certificate.issued_at >= date(year, 1, 1),
            Certificate.issued_at <= date(year, 12, 31),
        )
    rows = list(await db.scalars(q))
    ismlar = {u.id: u.full_name for u in await db.scalars(select(User))}
    return [
        CertificateOut(
            id=c.id,
            user_id=c.user_id,
            user_name=ismlar.get(c.user_id, "—"),
            purpose=c.purpose,
            purpose_label=CERTIFICATE_PURPOSE_LABELS.get(c.purpose, c.purpose),
            number=c.number,
            include_salary=c.include_salary,
            issued_at=c.issued_at,
            request_id=c.request_id,
            document_id=c.document_id,
            created_at=c.created_at,
        )
        for c in rows
    ]


@router.post("", status_code=status.HTTP_201_CREATED)
async def issue_certificate(
    payload: IssueIn,
    actor: User = Depends(require_roles(*_HR)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """HR ning ARIZASIZ berish yo'li — xodim og'zaki so'ragan holat.

    Ariza orqali kelgani avtomatik chiqadi va bu endpoint kerak emas."""
    from api.timeutil import today_local

    if payload.purpose not in CERTIFICATE_PURPOSE_LABELS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Noma'lum maqsad")
    target = await db.get(User, payload.user_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Xodim topilmadi")

    cert, tmpl = await svc.issue(
        db,
        user=target,
        purpose=payload.purpose,
        include_salary=payload.include_salary,
        today=today_local(),
        issued_by=actor.id,
    )
    await db.commit()
    return {
        "id": cert.id,
        "number": cert.number,
        "queued": tmpl is not None,
        #  Shablon yo'q bo'lsa raqam baribir beriladi — arxivda iz qoladi
        #  va HR hujjatni qo'lda tayyorlaydi.
        "note": None
        if tmpl is not None
        else "«reference» turidagi shablon yuklanmagan — hujjat qo'lda tayyorlanadi",
    }
