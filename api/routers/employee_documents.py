"""Kadr hujjatlari arxivi (yangi TZ 3.4 / S-10).

MUAMMO
──────
Hujjatlar HR ning shaxsiy Telegram yozishmalarida va qog'oz papkasida.
«Falonchining mehnat shartnomasi qani?» degan savol har safar qidiruvga
aylanadi; ishdan bo'shaganda mol-mulk dalolatnomasi topilmaydi.

⚠️ FAYL SERVERDA SAQLANMAYDI — faqat Telegram `file_id` (disk kvotasi
1 GB, TZ 1.1). Fayl Telegram'ning o'zida qoladi.

⚠️ RUXSAT — MODULNING ENG NOZIK JOYI
Bu maxfiy ma'lumot: diplom, tibbiy ma'lumotnoma, shartnoma. Shuning
uchun S-06 qatlami `rop_sees_team=False` bilan chaqiriladi — ROP bu
modulda «begona», o'z jamoasining hujjatini ham KO'RMAYDI. Begona
so'ralganda 403 emas, **404** qaytadi: 403 «bu odamda hujjat bor»
degan ma'lumotni oshkor qilardi.
"""
from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import assert_can_view, get_current_user, get_db, require_roles
from db.models import (
    DOCUMENT_TYPE_LABELS,
    DocumentType,
    EmployeeDocument,
    Role,
    User,
)

router = APIRouter(prefix="/employee-documents", tags=["employee-documents"])

#  Yuklash va boshqa xodimning hujjatini ko'rish — faqat shu rollar.
#  ROP ataylab YO'Q (yuqoridagi izohga qarang).
_HR = (Role.hr.value, Role.boss.value, Role.dasturchi.value)


class DocumentOut(BaseModel):
    id: int
    user_id: int
    doc_type: str
    doc_type_label: str
    name: str
    file_id: str
    file_type: str
    issued_at: date | None
    expires_at: date | None
    note: str | None
    uploaded_by: int | None
    created_at: datetime
    #  Muddati o'tgan / o'tayotgan hujjat ro'yxatda ajratib ko'rsatilsin
    #  (S-11 qabul mezoni). Hisob SERVERDA: uch mijoz (web, bot, kabinet)
    #  bir xil javob bersin.
    is_expired: bool = False
    days_left: int | None = None


class DocumentIn(BaseModel):
    user_id: int
    doc_type: str
    name: str = Field(min_length=1, max_length=200)
    file_id: str = Field(min_length=1, max_length=512)
    file_type: str = "document"
    issued_at: date | None = None
    expires_at: date | None = None
    note: str | None = Field(default=None, max_length=500)


def _out(d: EmployeeDocument, today: date) -> DocumentOut:
    qoldi = (d.expires_at - today).days if d.expires_at else None
    return DocumentOut(
        id=d.id,
        user_id=d.user_id,
        doc_type=d.doc_type,
        doc_type_label=DOCUMENT_TYPE_LABELS.get(d.doc_type, d.doc_type),
        name=d.name,
        file_id=d.file_id,
        file_type=d.file_type,
        issued_at=d.issued_at,
        expires_at=d.expires_at,
        note=d.note,
        uploaded_by=d.uploaded_by,
        created_at=d.created_at,
        is_expired=qoldi is not None and qoldi < 0,
        days_left=qoldi,
    )


async def _list_for(db: AsyncSession, user_id: int) -> list[DocumentOut]:
    """Bitta xodimning hujjatlari. `deleted_at IS NULL` SHU YERDA —
    o'qish yo'llari shu funksiyadan o'tadi, ya'ni filtrni unutib bo'lmaydi."""
    from api.timeutil import today_local

    rows = await db.scalars(
        select(EmployeeDocument)
        .where(
            EmployeeDocument.user_id == user_id,
            EmployeeDocument.deleted_at.is_(None),
        )
        #  Muddati tugaydiganlar tepada (NULL — muddatsiz — oxirida),
        #  keyin yangi yuklangani.
        .order_by(EmployeeDocument.expires_at.is_(None), EmployeeDocument.expires_at,
                  EmployeeDocument.created_at.desc())
    )
    bugun = today_local()
    return [_out(d, bugun) for d in rows]


@router.get("/types")
async def document_types(_user: User = Depends(get_current_user)) -> list[dict]:
    """Tur ro'yxati — bot, web va kabinet shu yagona manbadan oladi."""
    return [
        {"value": t.value, "label": DOCUMENT_TYPE_LABELS[t.value]} for t in DocumentType
    ]


@router.get("/me", response_model=list[DocumentOut])
async def my_documents(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[DocumentOut]:
    """Xodimning O'Z hujjatlari — har qanday rol o'zinikini ko'radi."""
    return await _list_for(db, user.id)


@router.get("/user/{user_id}", response_model=list[DocumentOut])
async def user_documents(
    user_id: int,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[DocumentOut]:
    """Boshqa xodimning hujjatlari — faqat HR/Boshliq/Dasturchi.

    `rop_sees_team=False`: ROP o'z jamoasining hujjatini ham ko'rmaydi.
    O'zini so'rasa o'tadi (`scoped_user_ids` har doim `{actor.id}` ni
    qo'shadi) — ya'ni `/user/{o'zi}` va `/me` bir xil ishlaydi."""
    await assert_can_view(actor, user_id, db, rop_sees_team=False)
    return await _list_for(db, user_id)


@router.post("", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
async def add_document(
    payload: DocumentIn,
    actor: User = Depends(require_roles(*_HR)),
    db: AsyncSession = Depends(get_db),
) -> DocumentOut:
    from api.timeutil import today_local

    if payload.doc_type not in DOCUMENT_TYPE_LABELS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Noma'lum hujjat turi")
    if payload.file_type not in {"document", "photo"}:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Noma'lum fayl turi")
    target = await db.get(User, payload.user_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Xodim topilmadi")
    if (
        payload.issued_at
        and payload.expires_at
        and payload.expires_at < payload.issued_at
    ):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Tugash sanasi berilgan sanadan oldin bo'lishi mumkin emas",
        )

    doc = EmployeeDocument(
        user_id=payload.user_id,
        doc_type=payload.doc_type,
        name=payload.name.strip(),
        file_id=payload.file_id,
        file_type=payload.file_type,
        uploaded_by=actor.id,
        issued_at=payload.issued_at,
        expires_at=payload.expires_at,
        note=(payload.note or "").strip() or None,
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    return _out(doc, today_local())


@router.delete("/{doc_id}")
async def delete_document(
    doc_id: int,
    _actor: User = Depends(require_roles(*_HR)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """YUMSHOQ o'chirish. Kadr hujjatini butunlay yo'qotish huquqiy xavf —
    xato bosilgan «o'chirish» qaytarilishi kerak."""
    doc = await db.get(EmployeeDocument, doc_id)
    if doc is None or doc.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Topilmadi")
    doc.deleted_at = datetime.utcnow()
    await db.commit()
    return {"ok": True, "id": doc_id}
