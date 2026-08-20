"""Biriktirilgan mol-mulk (yangi TZ 3.11 / S-18).

Noutbuk, telefon, SIM-karta va asbob kimdaligi hech qayerda yozilmagan.
Xodim ishdan bo'shaganda «unda nima bor edi?» degan savolga javob yo'q va
buyum shunchaki yo'qoladi.

⚠️ BITTA BUYUM — BITTA XODIMDA. Qo'riqchi IKKI QATLAMLI:
  1. kod tekshiradi va tushunarli xato beradi («hozir falonchida»);
  2. qisman unikal indeks (`returned_at IS NULL`) bazada kafolatlaydi.
Faqat birinchisiga tayanish yetarli emas: parallel ikki so'rov tekshiruvdan
birga o'tib, ikkita ochiq biriktirish yaratishi mumkin edi.

⚠️ RUXSAT: mol-mulk — kadr ma'lumoti (kimda nima bor). Kadr hujjatlari
bilan bir xil qamrov: HR/Boshliq/Dasturchi. ROP ko'rmaydi.
"""
from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user, get_db, require_roles
from api.timeutil import today_local
from db.models import (
    ASSET_CONDITION_LABELS,
    ASSET_KIND_LABELS,
    Asset,
    AssetAssignment,
    AssetCondition,
    Role,
    User,
)

router = APIRouter(prefix="/assets", tags=["assets"])

_HR = (Role.hr.value, Role.boss.value, Role.dasturchi.value)


class AssetOut(BaseModel):
    id: int
    inventory_no: str
    name: str
    kind: str
    kind_label: str
    condition: str
    condition_label: str
    value: int | None
    note: str | None
    #  Hozir kimda. `None` — omborda.
    holder_id: int | None
    holder_name: str | None
    assigned_at: date | None
    #  Xodim «Qabul qildim» bosganmi (S-19).
    accepted: bool


class AssetIn(BaseModel):
    inventory_no: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=200)
    kind: str
    condition: str = AssetCondition.good.value
    value: int | None = Field(default=None, ge=0)
    note: str | None = Field(default=None, max_length=500)


class AssignIn(BaseModel):
    user_id: int
    assigned_at: date | None = None
    condition_out: str = AssetCondition.good.value
    note: str | None = Field(default=None, max_length=500)


class ReturnIn(BaseModel):
    returned_at: date | None = None
    condition_in: str = AssetCondition.good.value
    note: str | None = Field(default=None, max_length=500)


class HistoryOut(BaseModel):
    id: int
    user_id: int
    user_name: str
    assigned_at: date
    returned_at: date | None
    condition_out: str
    condition_in: str | None
    accepted_at: datetime | None
    note: str | None


async def _open_map(db: AsyncSession) -> dict[int, AssetAssignment]:
    """Har buyumning OCHIQ biriktirishi (`returned_at IS NULL`).

    Bitta so'rovda olinadi — buyumlar ro'yxati uchun N+1 bo'lmasin."""
    rows = await db.scalars(
        select(AssetAssignment).where(AssetAssignment.returned_at.is_(None))
    )
    return {a.asset_id: a for a in rows}


def _out(a: Asset, band: AssetAssignment | None, ismlar: dict[int, str]) -> AssetOut:
    return AssetOut(
        id=a.id,
        inventory_no=a.inventory_no,
        name=a.name,
        kind=a.kind,
        kind_label=ASSET_KIND_LABELS.get(a.kind, a.kind),
        condition=a.condition,
        condition_label=ASSET_CONDITION_LABELS.get(a.condition, a.condition),
        value=a.value,
        note=a.note,
        holder_id=band.user_id if band else None,
        holder_name=ismlar.get(band.user_id) if band else None,
        assigned_at=band.assigned_at if band else None,
        accepted=bool(band and band.accepted_at),
    )


@router.get("/kinds")
async def kinds(_actor: User = Depends(require_roles(*_HR))) -> dict:
    return {
        "kinds": [{"value": k, "label": v} for k, v in ASSET_KIND_LABELS.items()],
        "conditions": [
            {"value": k, "label": v} for k, v in ASSET_CONDITION_LABELS.items()
        ],
    }


@router.get("", response_model=list[AssetOut])
async def list_assets(
    free_only: bool = False,
    _actor: User = Depends(require_roles(*_HR)),
    db: AsyncSession = Depends(get_db),
) -> list[AssetOut]:
    """Buyumlar ro'yxati. `free_only` — faqat omborda turganlari
    (biriktirish oynasi shundan tanlaydi)."""
    rows = list(
        await db.scalars(
            select(Asset)
            .where(Asset.deleted_at.is_(None))
            .order_by(Asset.kind, Asset.name)
        )
    )
    band = await _open_map(db)
    ismlar = {u.id: u.full_name for u in await db.scalars(select(User))}
    out = [_out(a, band.get(a.id), ismlar) for a in rows]
    return [x for x in out if x.holder_id is None] if free_only else out


@router.post("", response_model=AssetOut, status_code=status.HTTP_201_CREATED)
async def add_asset(
    payload: AssetIn,
    actor: User = Depends(require_roles(*_HR)),
    db: AsyncSession = Depends(get_db),
) -> AssetOut:
    if payload.kind not in ASSET_KIND_LABELS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Noma'lum tur")
    if payload.condition not in ASSET_CONDITION_LABELS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Noma'lum holat")

    raqam = payload.inventory_no.strip()
    #  ⚠️ Tekshiruv YUMSHOQ o'chirilganlarni ham qamraydi: o'chirilgan
    #  buyumning raqamini qayta ishlatish tarixni chalkashtiradi.
    if await db.scalar(select(Asset.id).where(Asset.inventory_no == raqam)):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"«{raqam}» inventar raqami allaqachon ishlatilgan",
        )

    a = Asset(
        inventory_no=raqam,
        name=payload.name.strip(),
        kind=payload.kind,
        condition=payload.condition,
        value=payload.value,
        note=(payload.note or "").strip() or None,
        created_by=actor.id,
    )
    db.add(a)
    try:
        await db.commit()
    except IntegrityError:
        #  Parallel so'rov bizdan oldin o'sha raqamni yozib ulgurdi.
        await db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"«{raqam}» inventar raqami band"
        )
    await db.refresh(a)
    return _out(a, None, {})


@router.post("/{asset_id}/assign", response_model=AssetOut)
async def assign(
    asset_id: int,
    payload: AssignIn,
    actor: User = Depends(require_roles(*_HR)),
    db: AsyncSession = Depends(get_db),
) -> AssetOut:
    """Buyumni xodimga biriktiradi.

    ⚠️ Band buyumni ikkinchi xodimga biriktirib BO'LMAYDI (TZ qabul
    mezoni). Xato xabari kimda ekanini aytadi — HR o'sha odamdan
    qaytarib olishi kerakligini darhol bilsin."""
    if payload.condition_out not in ASSET_CONDITION_LABELS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Noma'lum holat")
    a = await db.get(Asset, asset_id)
    if a is None or a.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Buyum topilmadi")
    target = await db.get(User, payload.user_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Xodim topilmadi")

    ochiq = await db.scalar(
        select(AssetAssignment).where(
            AssetAssignment.asset_id == asset_id,
            AssetAssignment.returned_at.is_(None),
        )
    )
    if ochiq is not None:
        egasi = await db.get(User, ochiq.user_id)
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Bu buyum hozir «{egasi.full_name if egasi else ochiq.user_id}» da "
            f"({ochiq.assigned_at}). Avval qaytarib oling.",
        )

    row = AssetAssignment(
        asset_id=asset_id,
        user_id=payload.user_id,
        assigned_at=payload.assigned_at or today_local(),
        condition_out=payload.condition_out,
        note=(payload.note or "").strip() or None,
        created_by=actor.id,
    )
    db.add(row)
    try:
        await db.commit()
    except IntegrityError:
        #  2-qatlam: qisman unikal indeks. Parallel so'rov tekshiruvdan
        #  birga o'tib, ikkinchi ochiq biriktirish yaratmoqchi bo'ldi.
        await db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Bu buyum shu payt boshqa xodimga biriktirildi — ro'yxatni yangilang",
        )
    await db.refresh(row)
    ismlar = {payload.user_id: target.full_name}
    return _out(a, row, ismlar)


@router.post("/{asset_id}/return", response_model=AssetOut)
async def return_asset(
    asset_id: int,
    payload: ReturnIn,
    _actor: User = Depends(require_roles(*_HR)),
    db: AsyncSession = Depends(get_db),
) -> AssetOut:
    """Buyumni qaytarib oladi. Qator O'CHIRILMAYDI — tarix qoladi.

    Qaytarishdagi holat berishdagidan yomon bo'lsa, farq tarixda
    ko'rinib turadi (`condition_out` va `condition_in`)."""
    if payload.condition_in not in ASSET_CONDITION_LABELS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Noma'lum holat")
    a = await db.get(Asset, asset_id)
    if a is None or a.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Buyum topilmadi")

    ochiq = await db.scalar(
        select(AssetAssignment).where(
            AssetAssignment.asset_id == asset_id,
            AssetAssignment.returned_at.is_(None),
        )
    )
    if ochiq is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Bu buyum hech kimga biriktirilmagan"
        )

    ochiq.returned_at = payload.returned_at or today_local()
    ochiq.condition_in = payload.condition_in
    if payload.note:
        ochiq.note = ((ochiq.note or "") + " | " + payload.note.strip()).strip(" |")
    #  Buyumning JORIY holati qaytarishdagi holatga tenglashadi — keyingi
    #  biriktirishda HR haqiqiy holatni ko'radi.
    a.condition = payload.condition_in
    await db.commit()
    return _out(a, None, {})


@router.get("/{asset_id}/history", response_model=list[HistoryOut])
async def history(
    asset_id: int,
    _actor: User = Depends(require_roles(*_HR)),
    db: AsyncSession = Depends(get_db),
) -> list[HistoryOut]:
    """Buyumning to'liq tarixi — kimda bo'lgan, qanday holatda qaytgan."""
    rows = list(
        await db.scalars(
            select(AssetAssignment)
            .where(AssetAssignment.asset_id == asset_id)
            .order_by(AssetAssignment.assigned_at.desc(), AssetAssignment.id.desc())
        )
    )
    ismlar = {u.id: u.full_name for u in await db.scalars(select(User))}
    return [
        HistoryOut(
            id=r.id,
            user_id=r.user_id,
            user_name=ismlar.get(r.user_id, "—"),
            assigned_at=r.assigned_at,
            returned_at=r.returned_at,
            condition_out=r.condition_out,
            condition_in=r.condition_in,
            accepted_at=r.accepted_at,
            note=r.note,
        )
        for r in rows
    ]


@router.get("/me", response_model=list[AssetOut])
async def my_assets(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[AssetOut]:
    """Xodimga biriktirilgan buyumlar — HAR QANDAY rol o'zinikini ko'radi.

    ⚠️ Bu endpoint `_HR` bilan himoyalanmagan: xodim o'ziga nima
    berilganini bilishi kerak. Faqat O'ZINIKI qaytariladi."""
    ochiq = list(
        await db.scalars(
            select(AssetAssignment).where(
                AssetAssignment.user_id == user.id,
                AssetAssignment.returned_at.is_(None),
            )
        )
    )
    if not ochiq:
        return []
    buyumlar = {
        a.id: a
        for a in await db.scalars(
            select(Asset).where(Asset.id.in_([r.asset_id for r in ochiq]))
        )
    }
    ismlar = {user.id: user.full_name}
    return [
        _out(buyumlar[r.asset_id], r, ismlar) for r in ochiq if r.asset_id in buyumlar
    ]


@router.delete("/{asset_id}")
async def delete_asset(
    asset_id: int,
    _actor: User = Depends(require_roles(*_HR)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Hisobdan chiqarish (yumshoq). Biriktirilgan buyumni chiqarib
    bo'lmaydi — avval qaytarib olish kerak, aks holda «kimdadir, lekin
    hisobda yo'q» degan holat paydo bo'lardi."""
    a = await db.get(Asset, asset_id)
    if a is None or a.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Topilmadi")
    ochiq = await db.scalar(
        select(AssetAssignment.id).where(
            AssetAssignment.asset_id == asset_id,
            AssetAssignment.returned_at.is_(None),
        )
    )
    if ochiq:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Buyum xodimda — avval qaytarib oling, keyin hisobdan chiqaring",
        )
    a.deleted_at = datetime.utcnow()
    await db.commit()
    return {"ok": True}


# ─────────────────────────────────────────────────────────────
# S-19 — xodim tomoni, dalolatnoma va standart to'plam
# ─────────────────────────────────────────────────────────────

#  Dalolatnoma shabloniga uzatiladigan belgilar. Ro'yxat SHU YERDA —
#  HR shablon yozishdan oldin qaysi nomlar borligini bilishi kerak.
ASSET_ACT_PLACEHOLDERS: dict[str, str] = {
    "sana": "Dalolatnoma sanasi",
    "fish": "Xodim F.I.Sh.",
    "lavozim": "Xodim lavozimi",
    "buyum": "Buyum nomi",
    "inventar": "Inventar raqami",
    "turi": "Buyum turi",
    "holati": "Holati",
    "qiymati": "Qiymati (raqam)",
    "qiymati_sozda": "Qiymati, bo'sh joy bilan",
    "amal": "Amal (berildi / qaytarildi)",
}


class AcceptOut(BaseModel):
    ok: bool
    accepted_at: datetime


@router.post("/{asset_id}/accept", response_model=AcceptOut)
async def accept_asset(
    asset_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AcceptOut:
    """Xodim «Qabul qildim» bosadi — VAQT yoziladi (yangi TZ 3.11 / S-19).

    NEGA VAQT MUHIM: nizo chiqqanda «men buni olganim yo'q» degan da'voga
    javob shu yozuv bo'ladi. Shuning uchun uni FAQAT xodimning o'zi
    bosishi mumkin — HR boshqa birov nomidan tasdiqlay olmaydi.

    IDEMPOTENT: qayta bosilsa BIRINCHI vaqt saqlanib qoladi. Aks holda
    xodim tugmani qayta bosib sanani «yangilab» qo'yishi mumkin edi."""
    ochiq = await db.scalar(
        select(AssetAssignment).where(
            AssetAssignment.asset_id == asset_id,
            AssetAssignment.user_id == user.id,
            AssetAssignment.returned_at.is_(None),
        )
    )
    if ochiq is None:
        #  404, 403 emas: buyum boshqa odamda ekanini oshkor qilmaymiz.
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Sizga bunday buyum biriktirilmagan"
        )
    if ochiq.accepted_at is None:
        ochiq.accepted_at = datetime.utcnow()
        await db.commit()
    return AcceptOut(ok=True, accepted_at=ochiq.accepted_at)


class ActIn(BaseModel):
    template_id: int
    #  "out" — biriktirish dalolatnomasi, "in" — qaytarish.
    action: str = "out"


@router.post("/{asset_id}/act", status_code=status.HTTP_202_ACCEPTED)
async def build_act(
    asset_id: int,
    payload: ActIn,
    actor: User = Depends(require_roles(*_HR)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Biriktirish/qaytarish DALOLATNOMASI (S-14 mexanizmi bilan).

    So'rov ichida tayyorlanmaydi — navbatga qo'yiladi va HR ning
    Telegram'iga boradi (Passenger konkurentligi = 1)."""
    from api.services.background_jobs import enqueue
    from db.models import DocumentTemplate, Position

    if payload.action not in ("out", "in"):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Amal «out» yoki «in» bo'lishi kerak"
        )
    a = await db.get(Asset, asset_id)
    if a is None or a.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Buyum topilmadi")
    tmpl = await db.get(DocumentTemplate, payload.template_id)
    if tmpl is None or not tmpl.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Shablon topilmadi")

    #  Dalolatnoma OXIRGI harakat bo'yicha tuziladi: «out» uchun ochiq
    #  biriktirish, «in» uchun eng so'nggi qaytarilgani.
    shart = (
        AssetAssignment.returned_at.is_(None)
        if payload.action == "out"
        else AssetAssignment.returned_at.isnot(None)
    )
    band = await db.scalar(
        select(AssetAssignment)
        .where(AssetAssignment.asset_id == asset_id, shart)
        .order_by(AssetAssignment.id.desc())
        .limit(1)
    )
    if band is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Bu buyum hech kimga berilmagan"
            if payload.action == "out"
            else "Bu buyum hali qaytarilmagan",
        )

    xodim = await db.get(User, band.user_id)
    lavozim = ""
    if xodim is not None and xodim.position_id:
        pos = await db.get(Position, xodim.position_id)
        lavozim = pos.name if pos else ""
    holat = band.condition_in if payload.action == "in" else band.condition_out
    sana = band.returned_at if payload.action == "in" else band.assigned_at

    values = {
        "sana": sana.isoformat() if sana else today_local().isoformat(),
        "fish": xodim.full_name if xodim else "",
        "lavozim": lavozim,
        "buyum": a.name,
        "inventar": a.inventory_no,
        "turi": ASSET_KIND_LABELS.get(a.kind, a.kind),
        "holati": ASSET_CONDITION_LABELS.get(holat or "", holat or ""),
        "qiymati": str(a.value or ""),
        "qiymati_sozda": f"{a.value:,}".replace(",", " ") if a.value else "",
        "amal": "berildi" if payload.action == "out" else "qaytarildi",
    }
    yetishmayotgan = [n for n in (tmpl.placeholders or []) if n not in values]

    job = await enqueue(
        db,
        "document_render",
        {
            "template_id": payload.template_id,
            "values": values,
            "filename": f"dalolatnoma_{a.inventory_no}_{payload.action}",
        },
        actor.id,
    )
    await db.commit()
    return {"job_id": job.id, "queued": True, "missing": yetishmayotgan}


@router.get("/act-placeholders")
async def act_placeholders(_actor: User = Depends(require_roles(*_HR))) -> list[dict]:
    return [{"name": k, "label": v} for k, v in ASSET_ACT_PLACEHOLDERS.items()]


class StandardSetIn(BaseModel):
    position_id: int
    #  {tur: miqdor}. Bo'sh yuborilsa lavozim to'plami TOZALANADI.
    items: dict[str, int]


@router.get("/standard-set/{position_id}")
async def standard_set(
    position_id: int,
    _actor: User = Depends(require_roles(*_HR)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Lavozimga mos STANDART to'plam.

    NEGA KERAK: yangi xodim kelganda unga nima berish kerakligi HR
    xotirasidan tiklanadi va har safar bir narsa unutiladi (odatda
    SIM-karta). Ishdan bo'shaganda esa nima qaytarilishi kerakligi
    noma'lum bo'lib qoladi. Onboarding (3.2) va offboarding (3.7) shu
    ro'yxatdan foydalanadi."""
    from db.models import PositionAssetSet

    rows = list(
        await db.scalars(
            select(PositionAssetSet).where(PositionAssetSet.position_id == position_id)
        )
    )
    return {
        "position_id": position_id,
        "items": [
            {
                "kind": r.kind,
                "kind_label": ASSET_KIND_LABELS.get(r.kind, r.kind),
                "quantity": r.quantity,
                "note": r.note,
            }
            for r in rows
        ],
    }


@router.put("/standard-set")
async def set_standard_set(
    payload: StandardSetIn,
    _actor: User = Depends(require_roles(*_HR)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """To'plamni BUTUNLAY almashtiradi (yuborilmagan turlar o'chadi).

    Qisman yangilash emas: HR ro'yxatni to'liq ko'rib chiqadi va nima
    qolishini o'zi hal qiladi — yarim holat chalkashlik keltirardi."""
    from sqlalchemy import delete as _delete

    from db.models import Position, PositionAssetSet

    if await db.get(Position, payload.position_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Lavozim topilmadi")
    for kind, qty in payload.items.items():
        if kind not in ASSET_KIND_LABELS:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Noma'lum tur: {kind}")
        if qty < 1:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"«{ASSET_KIND_LABELS[kind]}» miqdori 1 dan kam bo'lishi mumkin emas — "
                "kerak bo'lmasa ro'yxatdan chiqaring",
            )

    await db.execute(
        _delete(PositionAssetSet).where(
            PositionAssetSet.position_id == payload.position_id
        )
    )
    for kind, qty in payload.items.items():
        db.add(PositionAssetSet(position_id=payload.position_id, kind=kind, quantity=qty))
    await db.commit()
    return {"ok": True, "count": len(payload.items)}


@router.get("/checklist/{user_id}")
async def checklist(
    user_id: int,
    _actor: User = Depends(require_roles(*_HR)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Xodimda standart to'plamdan nima BOR va nima YETISHMAYDI.

    Onboarding va offboarding shu javobdan foydalanadi: birinchisida
    «berish kerak», ikkinchisida «qaytarib olish kerak» ro'yxati."""
    from db.models import PositionAssetSet

    target = await db.get(User, user_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Xodim topilmadi")

    kerak: dict[str, int] = {}
    if target.position_id:
        for r in await db.scalars(
            select(PositionAssetSet).where(
                PositionAssetSet.position_id == target.position_id
            )
        ):
            kerak[r.kind] = r.quantity

    ochiq = list(
        await db.scalars(
            select(AssetAssignment).where(
                AssetAssignment.user_id == user_id,
                AssetAssignment.returned_at.is_(None),
            )
        )
    )
    buyumlar = (
        {
            a.id: a
            for a in await db.scalars(
                select(Asset).where(Asset.id.in_([r.asset_id for r in ochiq]))
            )
        }
        if ochiq
        else {}
    )

    bor: dict[str, int] = {}
    for r in ochiq:
        a = buyumlar.get(r.asset_id)
        if a is not None:
            bor[a.kind] = bor.get(a.kind, 0) + 1

    return {
        "user_id": user_id,
        "has_position": target.position_id is not None,
        "items": [
            {
                "kind": k,
                "kind_label": ASSET_KIND_LABELS.get(k, k),
                "required": kerak.get(k, 0),
                "held": bor.get(k, 0),
                "missing": max(0, kerak.get(k, 0) - bor.get(k, 0)),
            }
            #  Standartda bor turlar + xodimda bor, lekin standartda yo'q
            #  turlar (ular ham qaytarilishi kerak).
            for k in sorted(set(kerak) | set(bor))
        ],
    }
