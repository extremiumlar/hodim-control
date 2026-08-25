"""Buyruqlar reyestri — API (yangi TZ 3.21 / S-50).

⚠️ TAHRIRLASH ENDPOINTI YO'Q va bo'lmaydi (TZ qabul mezoni).
Chiqarilgan buyruq — imzolangan hujjat; xato bo'lsa u BEKOR
QILINADI va bekor qilish ham yangi buyruq bilan rasmiylashtiriladi.
Batafsil izoh — `db/models.py::Order` va `api/services/orders.py`.

⚠️ Marshrut tartibi: so'zli yo'llar `/{id}` dan OLDIN (S-28 tuzog'i).
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user, get_db, require_roles
from api.services import orders as svc
from db.models import ORDER_KIND_LABELS, Order, OrderKind, Role, User

router = APIRouter(prefix="/orders", tags=["orders"])

#  Buyruq chiqarish va reyestrni ko'rish — HR/Boshliq/Dasturchi.
#  ⚠️ ROP bu yerda YO'Q: buyruq kadr hujjati va unda ish haqi,
#  intizomiy jazo kabi maxfiy ma'lumot bo'ladi (TZ 3.21 / S-51).
_HR = (Role.hr.value, Role.boss.value, Role.dasturchi.value)


class OrderIn(BaseModel):
    kind: str
    order_date: date
    user_id: int | None = None
    params: dict | None = None
    note: str | None = None


class CancelIn(BaseModel):
    reason: str
    order_date: date | None = None


@router.get("/kinds")
async def kinds(_actor: User = Depends(require_roles(*_HR))) -> list[dict]:
    return [{"value": k, "label": v} for k, v in ORDER_KIND_LABELS.items()]


@router.get("/stats")
async def stats(
    _actor: User = Depends(require_roles(*_HR)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await svc.stats(db)


@router.get("/me")
async def my_orders(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[dict]:
    """Xodim FAQAT O'ZIGA tegishli buyruqlarni ko'radi (TZ 3.21)."""
    return await svc.listing(db, user_id=user.id)


@router.get("")
async def list_orders(
    kind: str | None = None,
    user_id: int | None = None,
    _actor: User = Depends(require_roles(*_HR)),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    return await svc.listing(db, user_id=user_id, kind=kind)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_order(
    payload: OrderIn,
    actor: User = Depends(require_roles(*_HR)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Buyruq chiqaradi — RAQAM tizim tomonidan beriladi.

    ⚠️ Raqam so'rovda QABUL QILINMAYDI. Aks holda HR uni qo'lda
    kiritib, tasodifan mavjud raqamni takrorlab qo'yardi."""
    if payload.kind == OrderKind.cancellation.value:
        #  ⚠️ Bekor qilish buyrug'i FAQAT `/cancel` orqali —
        #  u eski buyruqqa havolani ham qo'yadi. To'g'ridan-to'g'ri
        #  yaratilsa «nima bekor qilindi?» degan savol javobsiz
        #  qolardi.
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Bekor qilish buyrug'i «bekor qilish» amali orqali chiqariladi",
        )
    try:
        row = await svc.create(
            db,
            kind=payload.kind,
            order_date=payload.order_date,
            user_id=payload.user_id,
            params=payload.params,
            note=payload.note,
            created_by=actor.id,
        )
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
    return await svc.out(db, row)


@router.post("/{order_id}/cancel", status_code=status.HTTP_201_CREATED)
async def cancel_order(
    order_id: int,
    payload: CancelIn,
    actor: User = Depends(require_roles(*_HR)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Buyruqni bekor qiladi va YANGI (bekor qiluvchi) buyruq chiqaradi."""
    row = await db.get(Order, order_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Buyruq topilmadi")
    try:
        yangi = await svc.cancel(
            db, order=row, reason=payload.reason,
            order_date=payload.order_date, created_by=actor.id,
        )
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
    return await svc.out(db, yangi)


@router.get("/{order_id}")
async def read_order(
    order_id: int,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Buyruq tafsiloti.

    ⚠️ Xodim FAQAT O'ZINIKINI ko'radi; begonasi uchun 404 (403
    EMAS — S-06 qoidasi: ketma-ket `id` larning mavjudligini
    oshkor qilmaslik)."""
    row = await db.get(Order, order_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Buyruq topilmadi")
    if actor.role not in _HR and row.user_id != actor.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Buyruq topilmadi")
    return await svc.out(db, row)
