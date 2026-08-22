"""Xodim murojaatlari jurnali — API (yangi TZ 3.29 / S-28).

Ikki ko'rinish qat'iy ajratilgan:
  • `/hr-inquiries/me*` — xodimniki. FAQAT o'z murojaatlari.
  • qolgani — HR/rahbar. Hammasi, javobsizlar tepada.

⚠️ BARCHA so'zli marshrutlar (`/me`, `/stats`, `/bot/...`)
`/{inquiry_id}` dan OLDIN e'lon qilinadi: FastAPI yo'lni E'LON
TARTIBIDA solishtiradi. `POST /bot/answer` ayniqsa xavfli edi — u
`POST /{inquiry_id}/answer` bilan bir xil shaklda va bir xil metodda,
ya'ni «bot» so'zi murojaat raqami deb o'qilib, bot hech qachon javob
yubora olmasdi (422).
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user, get_db, require_roles
from api.notify import notify_user
from api.services import hr_inquiries as svc
from api.services.push import Category
from db.models import (
    HR_INQUIRY_CATEGORY_LABELS,
    HrInquiry,
    HrInquiryCategory,
    HrInquiryStatus,
    Role,
    User,
)

router = APIRouter(prefix="/hr-inquiries", tags=["hr_inquiries"])

_HR = (Role.hr.value, Role.boss.value, Role.dasturchi.value)

_STATUS_LABELS = {
    HrInquiryStatus.open.value: "Javob kutilmoqda",
    HrInquiryStatus.answered.value: "Javob berilgan",
    HrInquiryStatus.closed.value: "Yopilgan",
}


class InquiryOut(BaseModel):
    id: int
    user_id: int
    user_name: str | None = None
    question: str
    answer: str | None
    category: str
    category_label: str
    category_auto: bool
    status: str
    status_label: str
    answered_by: int | None
    answered_by_name: str | None = None
    answered_at: datetime | None
    created_at: datetime


class AskIn(BaseModel):
    question: str = Field(min_length=5, max_length=svc.MAX_QUESTION_LEN)


class AnswerIn(BaseModel):
    answer: str = Field(min_length=1, max_length=svc.MAX_ANSWER_LEN)


class CategoryIn(BaseModel):
    category: str


def _out(row: HrInquiry, ismlar: dict[int, str]) -> InquiryOut:
    return InquiryOut(
        id=row.id,
        user_id=row.user_id,
        user_name=ismlar.get(row.user_id),
        question=row.question,
        answer=row.answer,
        category=row.category,
        category_label=svc.category_label(row.category),
        category_auto=row.category_auto,
        status=row.status,
        status_label=_STATUS_LABELS.get(row.status, row.status),
        answered_by=row.answered_by,
        answered_by_name=ismlar.get(row.answered_by) if row.answered_by else None,
        answered_at=row.answered_at,
        created_at=row.created_at,
    )


async def _names(db: AsyncSession) -> dict[int, str]:
    return {u.id: u.full_name for u in await db.scalars(select(User))}


# ─────────────────────────────────────────────────────────────
# XODIM
# ─────────────────────────────────────────────────────────────


@router.get("/categories")
async def categories(_user: User = Depends(get_current_user)) -> list[dict]:
    return [
        {"value": c.value, "label": HR_INQUIRY_CATEGORY_LABELS[c.value]}
        for c in HrInquiryCategory
    ]


@router.get("/me", response_model=list[InquiryOut])
async def my_inquiries(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[InquiryOut]:
    """Faqat O'Z murojaatlarim. Boshqaniki hech qachon ko'rinmaydi."""
    rows = await svc.for_user(db, user.id)
    ismlar = await _names(db)
    return [_out(r, ismlar) for r in rows]


async def _ask(db: AsyncSession, user: User, question: str) -> dict:
    """Savolni yozadi va HR ga xabar beradi.

    Sayt ham, bot ham SHU funksiyani chaqiradi — aks holda ikki joyda
    ikki xil xabar matni va ikki xil xatolik ishlovi paydo bo'lardi."""
    try:
        row = await svc.create(db, user_id=user.id, question=question)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e

    #  ⚠️ Qiymatlarni commitdan OLDIN olamiz: `commit()` obyektni
    #  eskirtiradi va keyingi atribut o'qish async kontekstda
    #  `MissingGreenlet` bilan yiqilardi.
    qabul = {
        "id": row.id,
        "category": row.category,
        "category_label": svc.category_label(row.category),
    }
    matn = (row.question or "")[:300]
    kimdan = user.full_name
    await db.commit()

    #  HR ga xabar. Xabar ketmasa ham savol SAQLANGAN — HR panelida
    #  javobsizlar ro'yxati bor, murojaat yo'qolmaydi.
    hrlar = await svc.hr_recipients(db)
    #  «Javob berish» tugmasi xabarning O'ZIDA: HR panelni ochib,
    #  murojaatni qidirib topmasin — javob berish yo'li qancha uzun
    #  bo'lsa, javobsiz murojaat shuncha ko'p qoladi.
    tugma = {
        "inline_keyboard": [
            [{"text": "✍️ Javob berish", "callback_data": f"hrq:ans:{qabul['id']}"}]
        ]
    }
    for hr in hrlar:
        await notify_user(
            db,
            hr,
            Category.APPROVALS,
            f"❓ <b>Yangi murojaat</b> — {kimdan}\n"
            f"Toifa: {qabul['category_label']}\n\n{matn}",
            title="Yangi murojaat",
            reply_markup=tugma,
            #  Javob berish hozircha faqat botda — ilovada bu ekran yo'q,
            #  shuning uchun Telegram HAR DOIM yuborilsin.
            force_telegram=True,
            data={"path": "/hr-inquiries"},
        )
    await db.commit()
    return {**qabul, "notified": len(hrlar)}


@router.post("/me", status_code=status.HTTP_201_CREATED)
async def ask(
    payload: AskIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Yangi savol. HR ga darhol xabar ketadi."""
    return await _ask(db, user, payload.question)


# ─────────────────────────────────────────────────────────────
# HR
# ─────────────────────────────────────────────────────────────


@router.get("", response_model=list[InquiryOut])
async def listing(
    status_filter: str | None = None,
    category: str | None = None,
    _actor: User = Depends(require_roles(*_HR)),
    db: AsyncSession = Depends(get_db),
) -> list[InquiryOut]:
    """HR ro'yxati — JAVOBSIZLAR BIRINCHI (TZ qabul mezoni)."""
    rows = await svc.listing(db, status=status_filter, category=category)
    ismlar = await _names(db)
    return [_out(r, ismlar) for r in rows]


@router.get("/stats")
async def stats(
    _actor: User = Depends(require_roles(*_HR)), db: AsyncSession = Depends(get_db)
) -> dict:
    return {"open": await svc.open_count(db)}


async def _get(db: AsyncSession, inquiry_id: int) -> HrInquiry:
    row = await db.get(HrInquiry, inquiry_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Murojaat topilmadi")
    return row


async def _answer(db: AsyncSession, row: HrInquiry, text: str, actor_id: int) -> dict:
    """Javobni yozadi va xodimga qaytaradi (sayt ham, bot ham shu yerdan)."""
    try:
        await svc.answer(db, inquiry=row, text=text, actor_id=actor_id)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e

    savol = (row.question or "")[:200]
    javob = row.answer or ""
    xodim_id = row.user_id
    await db.commit()

    xodim = await db.get(User, xodim_id)
    yuborildi = False
    if xodim is not None:
        await notify_user(
            db,
            xodim,
            Category.DECISIONS,
            f"✅ <b>HR javob berdi</b>\n\n<i>Savolingiz:</i> {savol}\n\n{javob}",
            title="HR javobi",
            data={"path": "/me/inquiries"},
        )
        yuborildi = True
        await db.commit()
    return {"ok": True, "delivered": yuborildi}


# ─────────────────────────────────────────────────────────────
# BOT
#
# Bot JWT ishlatmaydi — `telegram_id` bo'yicha kiradi (loyihadagi
# mavjud naqsh, `employee_documents.py::_bot_actor`). Mantiq yuqoridagi
# `_ask` / `_answer` bilan BIR XIL: ikki nusxa yozilsa, xabar matni yoki
# tekshiruv birida o'zgarib, ikkinchisida eskirib qolardi.
# ─────────────────────────────────────────────────────────────


class BotAskIn(BaseModel):
    telegram_id: int
    question: str = Field(min_length=5, max_length=svc.MAX_QUESTION_LEN)


class BotAnswerIn(BaseModel):
    telegram_id: int
    inquiry_id: int
    answer: str = Field(min_length=1, max_length=svc.MAX_ANSWER_LEN)


async def _bot_actor(db: AsyncSession, telegram_id: int) -> User:
    user = await db.scalar(select(User).where(User.telegram_id == telegram_id))
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Foydalanuvchi topilmadi")
    return user


@router.post("/bot/ask", status_code=status.HTTP_201_CREATED)
async def bot_ask(payload: BotAskIn, db: AsyncSession = Depends(get_db)) -> dict:
    actor = await _bot_actor(db, payload.telegram_id)
    return await _ask(db, actor, payload.question)


@router.get("/bot/my", response_model=list[InquiryOut])
async def bot_my(telegram_id: int, db: AsyncSession = Depends(get_db)) -> list[InquiryOut]:
    actor = await _bot_actor(db, telegram_id)
    rows = await svc.for_user(db, actor.id)
    ismlar = await _names(db)
    return [_out(r, ismlar) for r in rows]


@router.get("/bot/open", response_model=list[InquiryOut])
async def bot_open(telegram_id: int, db: AsyncSession = Depends(get_db)) -> list[InquiryOut]:
    """HR uchun: javob kutayotgan murojaatlar."""
    actor = await _bot_actor(db, telegram_id)
    if actor.role not in _HR:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Ruxsat yo'q")
    rows = await svc.listing(db, status=HrInquiryStatus.open.value)
    ismlar = await _names(db)
    return [_out(r, ismlar) for r in rows]


@router.post("/bot/answer")
async def bot_answer(payload: BotAnswerIn, db: AsyncSession = Depends(get_db)) -> dict:
    actor = await _bot_actor(db, payload.telegram_id)
    if actor.role not in _HR:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Ruxsat yo'q")
    row = await _get(db, payload.inquiry_id)
    return await _answer(db, row, payload.answer, actor.id)


@router.post("/{inquiry_id}/answer")
async def answer(
    inquiry_id: int,
    payload: AnswerIn,
    actor: User = Depends(require_roles(*_HR)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Javob yozish — javob xodimga darhol qaytadi."""
    row = await _get(db, inquiry_id)
    return await _answer(db, row, payload.answer, actor.id)


@router.put("/{inquiry_id}/category")
async def set_category(
    inquiry_id: int,
    payload: CategoryIn,
    _actor: User = Depends(require_roles(*_HR)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    row = await _get(db, inquiry_id)
    try:
        await svc.set_category(db, inquiry=row, category=payload.category)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
    await db.commit()
    return {"ok": True, "category": payload.category}


@router.post("/{inquiry_id}/close")
async def close(
    inquiry_id: int,
    _actor: User = Depends(require_roles(*_HR)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Javobsiz yopish (takroriy/ahamiyatsiz savol)."""
    row = await _get(db, inquiry_id)
    try:
        await svc.close(db, inquiry=row)
    except ValueError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    await db.commit()
    return {"ok": True}

