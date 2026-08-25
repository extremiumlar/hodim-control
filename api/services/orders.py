"""Buyruqlar reyestri — mantiq (yangi TZ 3.21 / S-50).

═══════════════════════════════════════════════════════════════
⚠️ RAQAM TAKRORLANMASLIGI — MODULNING ASOSIY VAZIFASI
═══════════════════════════════════════════════════════════════
Buyruq raqami huquqiy rekvizit. Ikkita buyruq bir xil raqam bilan
chiqsa, qaysi biri haqiqiy ekani noma'lum bo'ladi va tekshiruvda
bu jiddiy kamchilik.

Oddiy «MAX(number) + 1» YETARLI EMAS: ikki so'rov bir vaqtda kelsa
IKKALASI ham bir xil sonni ko'radi va bir xil raqam bilan yozadi.
cPanel'da bir necha jarayon bo'lishi mumkin (web + cron), ya'ni bu
nazariy xavf emas.

Himoya IKKI QATLAMLI:
  1. `orders.number` da UNIQUE cheklov — baza ikkinchisini RAD
     ETADI (kod xato bo'lsa ham dublikat yozilmaydi);
  2. shu yerdagi QAYTA URINISH — rad etilgan so'rov keyingi
     raqamni oladi va foydalanuvchi xato ko'rmaydi.

═══════════════════════════════════════════════════════════════
⚠️ BUYRUQ TAHRIRLANMAYDI
═══════════════════════════════════════════════════════════════
Chiqarilgan buyruq — imzolangan hujjat. `update` funksiyasi
ATAYLAB yozilmagan (S-39 dagi yo'riqnoma qoidasi bilan bir xil
sabab). Xato bo'lsa buyruq BEKOR QILINADI va bekor qilish ham
YANGI BUYRUQ bilan rasmiylashtiriladi — kadr ishida aynan
shunday.
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import (
    ORDER_KIND_LABELS,
    Order,
    OrderKind,
    OrderStatus,
    User,
)

logger = logging.getLogger(__name__)

#  Raqam ko'rinishi: «2026-001». Yil almashganda hisob NOLDAN
#  boshlanadi — kadr ishida buyruqlar yillik reyestrda yuritiladi.
NUMBER_FORMAT = "{year}-{seq:03d}"
_NUMBER_RE = re.compile(r"^(\d{4})-(\d+)$")

#  ⚠️ Qayta urinish soni. Parallel so'rovlar ko'p bo'lsa bir necha
#  marta to'qnashish mumkin; 8 ta urinish 8 ta bir vaqtdagi
#  so'rovga yetadi va cheksiz halqa ham bo'lmaydi.
MAX_RETRY = 8


def kind_label(value: str) -> str:
    return ORDER_KIND_LABELS.get(value, value)


async def _next_seq(db: AsyncSession, year: int) -> int:
    """Shu yildagi eng katta ketma-ket raqam + 1.

    ⚠️ Bu qiymat KAFOLAT EMAS — u faqat TAXMIN. Haqiqiy kafolat
    bazadagi UNIQUE cheklovda; bu yerda shunchaki keyingi bo'sh
    raqamni topamiz."""
    prefix = f"{year}-"
    raqamlar = list(
        await db.scalars(select(Order.number).where(Order.number.like(f"{prefix}%")))
    )
    eng_katta = 0
    for n in raqamlar:
        m = _NUMBER_RE.match(n or "")
        if m and int(m.group(1)) == year:
            eng_katta = max(eng_katta, int(m.group(2)))
    return eng_katta + 1


async def create(
    db: AsyncSession,
    *,
    kind: str,
    order_date: date,
    user_id: int | None = None,
    params: dict | None = None,
    note: str | None = None,
    file_id: str | None = None,
    cancels_order_id: int | None = None,
    cancel_reason: str | None = None,
    created_by: int | None = None,
) -> Order:
    """Buyruq yaratadi va RAQAM beradi.

    ⚠️ HAR URINISH O'Z TRANZAKSIYASIDA yakunlanadi (`commit`).
    Sabab: `IntegrityError` dan keyin sessiya ISHLATIB BO'LMAYDIGAN
    holatga tushadi va uni `rollback` bilan tozalash SHART. Bitta
    umumiy tranzaksiyada urinsak, birinchi to'qnashuvdan keyin
    chaqiruvchining boshqa o'zgarishlari ham yo'qolardi.

    Xatolar `ValueError` bilan."""
    if kind not in ORDER_KIND_LABELS:
        raise ValueError(f"Noma'lum buyruq turi: {kind}")

    yil = order_date.year
    for urinish in range(MAX_RETRY):
        seq = await _next_seq(db, yil)
        raqam = NUMBER_FORMAT.format(year=yil, seq=seq)
        row = Order(
            number=raqam,
            kind=kind,
            user_id=user_id,
            order_date=order_date,
            params=params or None,
            file_id=file_id,
            status=OrderStatus.active.value,
            cancels_order_id=cancels_order_id,
            cancel_reason=(cancel_reason or "").strip() or None,
            note=(note or "").strip() or None,
            created_by=created_by,
        )
        db.add(row)
        try:
            await db.commit()
        except IntegrityError:
            #  ⚠️ Boshqa so'rov shu raqamni bizdan oldin oldi. Bu
            #  XATO EMAS — kutilgan poyga. Sessiyani tozalab,
            #  keyingi raqamni olamiz.
            await db.rollback()
            logger.info(
                "Buyruq raqami band edi (%s), qayta urinilmoqda (%s)",
                raqam,
                urinish + 1,
            )
            continue
        await db.refresh(row)
        return row

    raise ValueError(
        f"Buyruq raqamini {MAX_RETRY} urinishda ham olib bo'lmadi — "
        "keyinroq qayta urinib ko'ring"
    )


async def cancel(
    db: AsyncSession,
    *,
    order: Order,
    reason: str,
    order_date: date | None = None,
    created_by: int | None = None,
) -> Order:
    """Buyruqni bekor qiladi va BEKOR QILISH BUYRUG'INI chiqaradi.

    ⚠️ TAHRIRLASH O'RNIGA SHU. Eski buyruq o'chirilmaydi va
    o'zgartirilmaydi — u `cancelled` holatiga o'tadi, matni esa
    o'sha holicha qoladi. Reyestrda ikkala yozuv ham ko'rinadi:
    «nima chiqarilgan» va «nima bilan bekor qilingan».

    Xatolar `ValueError` bilan."""
    from api.timeutil import today_local

    if order.status != OrderStatus.active.value:
        raise ValueError("Bu buyruq allaqachon bekor qilingan")
    if not (reason or "").strip():
        raise ValueError("Bekor qilish sababi kiritilishi shart")

    #  ⚠️ AVVAL BEKOR QILISH BUYRUG'I yaratiladi (u `commit`
    #  qiladi), keyin eski buyruq belgilanadi. Teskari tartibda
    #  yangi buyruq yaratilmay qolsa, eski buyruq bekor
    #  ko'rinardi-yu, bekor qiluvchi hujjat bo'lmasdi.
    yangi = await create(
        db,
        kind=OrderKind.cancellation.value,
        order_date=order_date or today_local(),
        user_id=order.user_id,
        cancels_order_id=order.id,
        cancel_reason=reason,
        note=f"«{order.number}» sonli buyruq bekor qilindi",
        created_by=created_by,
    )
    order.status = OrderStatus.cancelled.value
    await db.commit()
    return yangi


async def out(db: AsyncSession, row: Order, names: dict[int, str] | None = None) -> dict:
    ismlar = names
    if ismlar is None:
        ismlar = {u.id: u.full_name for u in await db.scalars(select(User))}
    return {
        "id": row.id,
        "number": row.number,
        "kind": row.kind,
        "kind_label": kind_label(row.kind),
        "user_id": row.user_id,
        "full_name": ismlar.get(row.user_id) if row.user_id else None,
        "order_date": row.order_date,
        "params": row.params or {},
        "file_id": row.file_id,
        "status": row.status,
        "cancels_order_id": row.cancels_order_id,
        "cancel_reason": row.cancel_reason,
        "note": row.note,
        "created_by": row.created_by,
        "created_at": row.created_at,
    }


async def listing(
    db: AsyncSession,
    *,
    user_id: int | None = None,
    kind: str | None = None,
    limit: int = 200,
) -> list[dict]:
    """Reyestr — yangisidan eskisiga.

    ⚠️ BEKOR QILINGANLAR HAM KO'RINADI. Reyestr — tarix, undan
    yozuv yo'qolmasligi kerak; holat ustunida farqi ko'rinadi."""
    q = select(Order).order_by(Order.order_date.desc(), Order.id.desc()).limit(limit)
    if user_id is not None:
        q = q.where(Order.user_id == user_id)
    if kind:
        q = q.where(Order.kind == kind)
    rows = list(await db.scalars(q))
    ismlar = {u.id: u.full_name for u in await db.scalars(select(User))}
    return [await out(db, r, ismlar) for r in rows]


async def stats(db: AsyncSession) -> dict:
    """Reyestr yig'masi — tur va holat bo'yicha."""
    turlar = {
        k: v
        for k, v in (
            await db.execute(select(Order.kind, func.count(Order.id)).group_by(Order.kind))
        ).all()
    }
    holatlar = {
        k: v
        for k, v in (
            await db.execute(
                select(Order.status, func.count(Order.id)).group_by(Order.status)
            )
        ).all()
    }
    return {
        "total": sum(turlar.values()),
        "by_kind": {k: {"label": kind_label(k), "count": v} for k, v in turlar.items()},
        "by_status": holatlar,
    }
