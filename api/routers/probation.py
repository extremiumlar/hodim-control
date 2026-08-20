"""Sinov muddatidagi xodimlar ro'yxati (yangi TZ 3.24 / S-24).

⚠️ YANGI JADVAL YO'Q (TZ 1-band). Ro'yxat butunlay HISOBLANADI:
`users.hire_date` + sinov muddati. Saqlansa u darhol eskirardi —
`hire_date` tuzatilsa nusxa eski qolib ketardi (S-12 dagi «ikkita manba
bo'lmasin» qoidasi bilan bir xil sabab).

⚠️ SINOV MUDDATI QAYERDAN OLINADI (TZ 3-qabul mezoni: hujjatlashtirish
talab qilinadi):

  1. AGAR xodim ish taklifi orqali kelgan bo'lsa (`offers.user_id`) —
     o'sha taklifdagi `probation_months` ishlatiladi. Bu xodim bilan
     ANIQ kelishilgan muddat, ya'ni eng ishonchli manba.
  2. Aks holda — `deadline_config.probation_days` (default 90 kun),
     HR sozlaydigan umumiy qiymat. Aynan shu qiymat S-12 dagi muddat
     eslatmalarida ham ishlatiladi, ya'ni ikkalasi doim mos keladi.

Eslatmaning o'zi S-12 (`deadlines`) orqali boradi. Bu ro'yxat esa DOIM
ko'rinadi — eslatma o'tkazib yuborilgan bo'lsa ham (TZ qabul mezoni).
"""
from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_db, require_roles
from api.timeutil import today_local
from db.models import (
    Acknowledgement,
    Asset,
    AssetAssignment,
    DocumentType,
    EmployeeDocument,
    Offer,
    Position,
    PositionAssetSet,
    Role,
    User,
)

router = APIRouter(prefix="/probation", tags=["probation"])

_VIEW = (Role.hr.value, Role.boss.value, Role.dasturchi.value)


class ProbationOut(BaseModel):
    user_id: int
    full_name: str
    position_name: str | None
    hire_date: date
    ends_at: date
    days_left: int
    is_overdue: bool
    #  Muddat qayerdan olingani — HR «nega bu sana?» deb so'ramasin.
    source: str
    #  Onboarding holati. 3.2 moduli hali qurilmagan, shuning uchun
    #  MAVJUD ma'lumotdan yig'iladi: shartnoma bormi, mol-mulk
    #  to'plami to'liqmi, tanishtirishlar o'qilganmi. Modul tayyor
    #  bo'lgach shu maydonlar o'sha yerdan keladi.
    has_contract: bool
    assets_missing: int
    acks_pending: int
    #  Oraliq baho — alohida modul yo'q; HR `deadlines` izohiga yozadi.
    #  Bu yerda faqat «baho qo'yilganmi» bayrog'i bo'lardi, lekin uni
    #  soxta to'ldirmaslik uchun hozircha `None`.
    review: str | None = None


async def _probation_days_map(db: AsyncSession) -> dict[int, tuple[int, str]]:
    """Xodim -> (kun, manba). Taklifdan kelganlar birinchi navbatda."""
    from api.services.deadlines import get_config

    cfg = await get_config(db)
    default = (cfg.probation_days, "umumiy sozlama")
    out: dict[int, tuple[int, str]] = {}
    rows = await db.scalars(
        select(Offer).where(
            Offer.user_id.isnot(None), Offer.probation_months.isnot(None)
        )
    )
    for o in rows:
        #  Oy -> kun: 30 kunlik oy. Aniqroq hisob (kalendar oy) bu yerda
        #  ortiqcha — sinov muddati baribir taxminiy chegara va HR uni
        #  kun bilan boshqaradi.
        out[o.user_id] = (o.probation_months * 30, f"ish taklifi #{o.id}")
    return {**out, 0: default}  # 0 — kalit sifatida default


@router.get("", response_model=list[ProbationOut])
async def list_probation(
    include_finished: bool = False,
    _actor: User = Depends(require_roles(*_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> list[ProbationOut]:
    """Sinov muddatidagi xodimlar.

    `include_finished=True` — muddati o'tganlarni ham qo'shadi. Default
    ular ham KIRADI (chunki ular eng muhimi — qaror qabul qilinmagan),
    faqat allaqachon uzoq o'tib ketganlari chiqariladi."""
    bugun = today_local()
    kunlar = await _probation_days_map(db)
    default_kun, default_manba = kunlar[0]

    lavozimlar = {p.id: p.name for p in await db.scalars(select(Position))}
    xodimlar = list(
        await db.scalars(
            select(User).where(User.is_active.is_(True), User.hire_date.isnot(None))
        )
    )

    #  Onboarding belgilarini BITTA so'rovda yig'amiz (N+1 bo'lmasin).
    shartnomalar = {
        d.user_id
        for d in await db.scalars(
            select(EmployeeDocument).where(
                EmployeeDocument.deleted_at.is_(None),
                EmployeeDocument.doc_type == DocumentType.contract.value,
            )
        )
    }
    standart: dict[int, dict[str, int]] = {}
    for r in await db.scalars(select(PositionAssetSet)):
        standart.setdefault(r.position_id, {})[r.kind] = r.quantity
    buyum_turlari = {a.id: a.kind for a in await db.scalars(select(Asset))}
    bor_buyum: dict[int, dict[str, int]] = {}
    for r in await db.scalars(
        select(AssetAssignment).where(AssetAssignment.returned_at.is_(None))
    ):
        tur = buyum_turlari.get(r.asset_id)
        if tur:
            bor_buyum.setdefault(r.user_id, {})[tur] = (
                bor_buyum.get(r.user_id, {}).get(tur, 0) + 1
            )
    kutilayotgan_ack: dict[int, int] = {}
    for r in await db.scalars(
        select(Acknowledgement).where(Acknowledgement.acknowledged_at.is_(None))
    ):
        kutilayotgan_ack[r.user_id] = kutilayotgan_ack.get(r.user_id, 0) + 1

    out: list[ProbationOut] = []
    for u in xodimlar:
        kun, manba = kunlar.get(u.id, (default_kun, default_manba))
        tugash = u.hire_date + timedelta(days=kun)
        qoldi = (tugash - bugun).days
        #  Tugagandan keyin 30 kun ro'yxatda qoladi: qaror qabul
        #  qilinmagan bo'lsa u ko'rinib tursin (TZ: «muddati o'tganlar
        #  ajratib ko'rsatiladi»). Undan keyin chiqadi — aks holda
        #  ro'yxat eski xodimlar bilan to'lib ketardi.
        if qoldi < -30 and not include_finished:
            continue
        if qoldi > kun:  # kelajakda ishga chiqadigan xodim
            continue

        kerak = standart.get(u.position_id or 0, {})
        bor = bor_buyum.get(u.id, {})
        yetishmayotgan = sum(
            max(0, miqdor - bor.get(tur, 0)) for tur, miqdor in kerak.items()
        )

        out.append(
            ProbationOut(
                user_id=u.id,
                full_name=u.full_name,
                position_name=lavozimlar.get(u.position_id) if u.position_id else None,
                hire_date=u.hire_date,
                ends_at=tugash,
                days_left=qoldi,
                is_overdue=qoldi < 0,
                source=manba,
                has_contract=u.id in shartnomalar,
                assets_missing=yetishmayotgan,
                acks_pending=kutilayotgan_ack.get(u.id, 0),
            )
        )
    #  Muddati o'tganlar TEPADA — qaror ular bo'yicha kechikkan.
    out.sort(key=lambda p: p.days_left)
    return out


@router.get("/summary")
async def summary(
    _actor: User = Depends(require_roles(*_VIEW)), db: AsyncSession = Depends(get_db)
) -> dict:
    rows = await list_probation(include_finished=False, _actor=_actor, db=db)
    return {
        "total": len(rows),
        "overdue": sum(1 for r in rows if r.is_overdue),
        "ending_soon": sum(1 for r in rows if 0 <= r.days_left <= 7),
        #  Sozlama qayerdanligi javobda ham bor: HR panelda «nega bu
        #  sana?» degan savolga darhol javob topsin.
        "default_days": (await _probation_days_map(db))[0][0],
    }
