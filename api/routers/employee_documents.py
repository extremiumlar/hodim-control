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

from api.deps import assert_can_view, get_current_user, get_db, require_roles, verify_bot_secret
from db.models import (
    DOCUMENT_TYPE_LABELS,
    DocumentType,
    EmployeeDocument,
    Role,
    User,
)

router = APIRouter(prefix="/employee-documents", tags=["employee-documents"])

#  ⚠️ BOT ENDPOINTLARI UCHUN SIR QO'RIQCHISI — MAJBURIY.
#  Bu yo'llar xodimni `telegram_id` bo'yicha topadi, ya'ni JWT yo'q.
#  Sir tekshirilmasa istalgan kishi begona `telegram_id` yuborib
#  o'sha xodimning ma'lumotini o'qiy va uning NOMIDAN amal qila
#  olardi. Router darajasida qo'yib bo'lmaydi — shu routerda JWT
#  bilan ishlaydigan yo'llar ham bor.
_BOT_SIR = [Depends(verify_bot_secret)]

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


# ─────────────────────────────────────────────────────────────
# BOT (S-11) — autentifikatsiya `telegram_id` orqali
# (`api/routers/celebration.py` bilan bir xil naqsh: bot JWT
#  yuritmaydi, foydalanuvchini Telegram ID si bilan tanidiradi)
# ─────────────────────────────────────────────────────────────


class BotUploadIn(BaseModel):
    telegram_id: int
    user_id: int
    doc_type: str
    name: str = Field(min_length=1, max_length=200)
    file_id: str = Field(min_length=1, max_length=512)
    file_type: str = "document"
    expires_at: date | None = None


class BotSendIn(BaseModel):
    telegram_id: int
    doc_id: int


async def _bot_actor(db: AsyncSession, telegram_id: int) -> User:
    user = await db.scalar(select(User).where(User.telegram_id == telegram_id))
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Foydalanuvchi topilmadi")
    return user


@router.get("/bot/my", response_model=list[DocumentOut], dependencies=_BOT_SIR)
async def bot_my_documents(
    telegram_id: int, db: AsyncSession = Depends(get_db)
) -> list[DocumentOut]:
    """Botdagi «Hujjatlarim» — xodim o'z hujjatlarini ko'radi."""
    actor = await _bot_actor(db, telegram_id)
    return await _list_for(db, actor.id)


@router.get("/bot/types", dependencies=_BOT_SIR)
async def bot_document_types(
    telegram_id: int, db: AsyncSession = Depends(get_db)
) -> list[dict]:
    """Tur ro'yxati bot uchun. Bot o'z nusxasini yuritmaydi — yangi tur
    qo'shilganda bot eskisini ko'rsatib turmasin."""
    await _bot_actor(db, telegram_id)
    return [
        {"value": t.value, "label": DOCUMENT_TYPE_LABELS[t.value]} for t in DocumentType
    ]


@router.get("/bot/employees", dependencies=_BOT_SIR)
async def bot_employees(telegram_id: int, db: AsyncSession = Depends(get_db)) -> list[dict]:
    """HR hujjat yuklashda xodim tanlaydi. Faqat HR/Boshliq/Dasturchi."""
    actor = await _bot_actor(db, telegram_id)
    if actor.role not in _HR:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Ruxsat yo'q")
    rows = await db.scalars(
        select(User).where(User.is_active.is_(True)).order_by(User.full_name)
    )
    return [{"id": u.id, "full_name": u.full_name} for u in rows]


@router.post("/bot/upload", response_model=DocumentOut, status_code=status.HTTP_201_CREATED, dependencies=_BOT_SIR)
async def bot_upload(
    payload: BotUploadIn, db: AsyncSession = Depends(get_db)
) -> DocumentOut:
    """Botdan hujjat yuklash. Fayl Telegram'da qoladi — `file_id` keladi."""
    actor = await _bot_actor(db, payload.telegram_id)
    if actor.role not in _HR:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Ruxsat yo'q")
    return await add_document(
        DocumentIn(
            user_id=payload.user_id,
            doc_type=payload.doc_type,
            name=payload.name,
            file_id=payload.file_id,
            file_type=payload.file_type,
            expires_at=payload.expires_at,
        ),
        actor,
        db,
    )


@router.post("/bot/send", dependencies=_BOT_SIR)
async def bot_send_document(
    payload: BotSendIn, db: AsyncSession = Depends(get_db)
) -> dict:
    """Hujjatni EGASIGA Telegram orqali qaytarish.

    Fayl serverda yo'q — `file_id` bo'yicha qayta yuboriladi
    (`telegram_notify.send_file_id`), ya'ni so'rov oddiy JSON.

    ⚠️ Ruxsat SHU YERDA ham tekshiriladi: `doc_id` ni taxmin qilib
    boshqaning hujjatini o'ziga yuborib olish mumkin bo'lmasin."""
    from api.telegram_notify import send_file_id

    actor = await _bot_actor(db, payload.telegram_id)
    doc = await db.get(EmployeeDocument, payload.doc_id)
    if doc is None or doc.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Topilmadi")
    await assert_can_view(actor, doc.user_id, db, rop_sees_team=False)

    izoh = f"📄 <b>{doc.name}</b>\n{DOCUMENT_TYPE_LABELS.get(doc.doc_type, doc.doc_type)}"
    if doc.expires_at:
        izoh += f"\nAmal qiladi: {doc.expires_at.isoformat()} gacha"
    resp = await send_file_id(actor.telegram_id, doc.file_id, doc.file_type, caption=izoh)
    #  `resp is None` — bildirishnomalar o'chiq (test rejimi) yoki token yo'q.
    #  Bu XATO emas: chaqiruvchi «yuborildi» deb ko'rsatmasligi uchun bayroq.
    return {"ok": True, "delivered": resp is not None}


# ─────────────────────────────────────────────────────────────
# S-27 — shartnomani DAVLAT RO'YXATIDAN o'tkazish belgisi (TZ 3.28)
#
# ⚠️ TIZIM RO'YXATGA OLISHNI BAJARMAYDI. Bu tashqi jarayon (mehnat
# organi); tizim faqat «qilindimi?» degan BELGINI yuritadi. Aks holda
# HR uni bajarilgan deb o'ylab, aslida qilinmagan bo'lardi.
#
# «3 kun» — TZ dagi qiymat: shartnoma qonun bo'yicha ishga qabuldan
# keyin qisqa muddatda ro'yxatdan o'tkazilishi kerak.
# ─────────────────────────────────────────────────────────────

REGISTRATION_GRACE_DAYS = 3


class RegisterIn(BaseModel):
    registered_at: date | None = None
    note: str | None = Field(default=None, max_length=500)


class UnregisteredOut(BaseModel):
    user_id: int
    full_name: str
    hire_date: date | None
    days_since_hire: int | None
    #  Shartnoma hujjati BORmi. `None` — hujjat umuman yuklanmagan,
    #  ya'ni belgi qo'yadigan narsaning o'zi yo'q.
    document_id: int | None
    overdue: bool


@router.post("/{doc_id}/register")
async def mark_registered(
    doc_id: int,
    payload: RegisterIn,
    actor: User = Depends(require_roles(*_HR)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Shartnoma ro'yxatdan o'tkazilgani BELGISINI qo'yadi.

    ⚠️ Tizim ro'yxatga olishni bajarmaydi — HR uni tashqi organda
    bajarib, natijasini shu yerda belgilaydi.

    IDEMPOTENT: qayta bosilsa BIRINCHI sana saqlanadi. Aks holda belgi
    har bosishda «bugun» ga siljib, haqiqiy sana yo'qolardi."""
    from api.timeutil import today_local

    doc = await db.get(EmployeeDocument, doc_id)
    if doc is None or doc.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Hujjat topilmadi")
    if doc.doc_type != DocumentType.contract.value:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Ro'yxatga olish belgisi faqat mehnat shartnomasiga qo'yiladi",
        )
    sana = payload.registered_at or today_local()
    if sana > today_local():
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Kelajakdagi sana ko'rsatilmaydi"
        )

    if doc.registered_at is None:
        doc.registered_at = sana
        doc.registered_by = actor.id
        doc.registration_note = (payload.note or "").strip() or None
        await db.commit()
    return {
        "ok": True,
        "registered_at": doc.registered_at.isoformat(),
        "already": doc.registered_by != actor.id or doc.registered_at != sana,
    }


@router.get("/unregistered", response_model=list[UnregisteredOut])
async def unregistered(
    _actor: User = Depends(require_roles(*_HR)), db: AsyncSession = Depends(get_db)
) -> list[UnregisteredOut]:
    """Shartnomasi ro'yxatdan o'tkazilmagan xodimlar (TZ qabul mezoni).

    Ikki holat ham kiradi:
      • shartnoma hujjati umuman yuklanmagan;
      • hujjat bor, lekin belgi qo'yilmagan.
    Ikkalasi ham HR uchun bir xil ish — shuning uchun bitta ro'yxat.

    Kadr auditi (3.30) shu so'rovni qayta ishlatadi."""
    from api.timeutil import today_local

    bugun = today_local()
    xodimlar = list(
        await db.scalars(select(User).where(User.is_active.is_(True)))
    )
    shartnomalar: dict[int, EmployeeDocument] = {}
    for d in await db.scalars(
        select(EmployeeDocument).where(
            EmployeeDocument.deleted_at.is_(None),
            EmployeeDocument.doc_type == DocumentType.contract.value,
        )
    ):
        #  Bir xodimda bir necha shartnoma bo'lsa — RO'YXATDAN
        #  O'TKAZILGANI ustun. Aks holda eski qoralama tufayli xodim
        #  «belgisiz» bo'lib qolardi.
        bor = shartnomalar.get(d.user_id)
        if bor is None or (bor.registered_at is None and d.registered_at is not None):
            shartnomalar[d.user_id] = d

    out: list[UnregisteredOut] = []
    for u in xodimlar:
        doc = shartnomalar.get(u.id)
        if doc is not None and doc.registered_at is not None:
            continue
        kun = (bugun - u.hire_date).days if u.hire_date else None
        out.append(
            UnregisteredOut(
                user_id=u.id,
                full_name=u.full_name,
                hire_date=u.hire_date,
                days_since_hire=kun,
                document_id=doc.id if doc else None,
                overdue=kun is not None and kun > REGISTRATION_GRACE_DAYS,
            )
        )
    #  Eng ko'p kechikkani tepada.
    out.sort(key=lambda x: -(x.days_since_hire or 0))
    return out
