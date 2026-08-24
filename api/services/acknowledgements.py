"""«Tanishdim» qaydi — UMUMIY servis (yangi TZ / S-20).

Uchta modul shuni ishlatadi: lavozim yo'riqnomasi (3.16), ichki e'lon
(3.12) va TX instruktaji (3.6). Har biriga alohida jadval qilinsa «kim
nima bilan tanishmagan?» degan savolga uchta so'rov kerak bo'lardi va
yangi tur qo'shilganda to'rtinchisi.

⚠️ VERSIYA — MODULNING MARKAZIY G'OYASI
Yo'riqnoma yangilansa eski tanishuv O'TMAYDI: xodim eski matnga rozi
bo'lgan, yangisiga emas. Bu huquqiy jihatdan muhim — «u bilardi» degan
da'vo faqat u ko'rgan VERSIYAGA nisbatan o'rinli.

Qatorlar hech qachon o'chirilmaydi: eski versiyalar tarix bo'lib qoladi
va «o'sha paytda nimaga rozi bo'lgan edi?» degan savolga javob beradi.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import ACK_OBJECT_LABELS, Acknowledgement, User


@dataclass(frozen=True)
class PendingItem:
    """Xodim tanishishi kerak bo'lgan bitta band."""

    id: int
    object_type: str
    object_type_label: str
    object_id: int
    version: int
    title: str | None
    link: str | None
    requested_at: datetime


@dataclass(frozen=True)
class ReaderRow:
    """Obyekt bo'yicha bitta odamning holati."""

    user_id: int
    user_name: str
    version: int
    acknowledged_at: datetime | None


async def request_ack(
    db: AsyncSession,
    *,
    object_type: str,
    object_id: int,
    version: int,
    user_ids: list[int],
    title: str | None = None,
    link: str | None = None,
    requested_by: int | None = None,
) -> int:
    """Berilgan xodimlardan tanishishni SO'RAYDI.

    Qaytaradi: yangi yaratilgan qatorlar soni.

    ⚠️ IDEMPOTENT. Bir xil (xodim, obyekt, versiya) uchun ikkinchi qator
    yaratilmaydi — modul so'rovni takrorlasa (masalan e'lon qayta
    yuborilsa) xodimda ikkita bir xil band paydo bo'lmaydi. Himoya ikki
    qatlamli: avval mavjudlari tanlanadi, keyin UNIQUE cheklov.

    ⚠️ Chaqiruvchi COMMIT qiladi — so'rov manba obyektni yaratish bilan
    BITTA tranzaksiyada bo'lishi kerak, aks holda «e'lon bor, lekin hech
    kimdan so'ralmagan» holati paydo bo'lardi."""
    if object_type not in ACK_OBJECT_LABELS:
        raise ValueError(f"noma'lum obyekt turi: {object_type}")
    if not user_ids:
        return 0

    mavjud = {
        r
        for r in await db.scalars(
            select(Acknowledgement.user_id).where(
                Acknowledgement.object_type == object_type,
                Acknowledgement.object_id == object_id,
                Acknowledgement.version == version,
                Acknowledgement.user_id.in_(user_ids),
            )
        )
    }
    n = 0
    for uid in dict.fromkeys(user_ids):  # takrorlarni tashlaydi, tartibni saqlaydi
        if uid in mavjud:
            continue
        db.add(
            Acknowledgement(
                user_id=uid,
                object_type=object_type,
                object_id=object_id,
                version=version,
                title=title,
                link=link,
                requested_by=requested_by,
            )
        )
        n += 1
    if n:
        try:
            await db.flush()
        except IntegrityError:
            #  Parallel so'rov bizdan oldin yozib ulgurdi. Bu XATO EMAS:
            #  natija baribir kerakli holat (qator bor).
            await db.rollback()
            return 0
    return n


async def mark_ack(
    db: AsyncSession, *, user_id: int, object_type: str, object_id: int, version: int
) -> Acknowledgement | None:
    """Xodim «Tanishdim» bosdi.

    ⚠️ IDEMPOTENT: qayta bosilsa BIRINCHI vaqt saqlanadi. Aks holda
    xodim tugmani qayta bosib sanani «yangilab» qo'yishi mumkin edi va
    huquqiy qiymati yo'qolardi.

    So'ralmagan bandni tasdiqlab bo'lmaydi (`None` qaytadi): tanishish
    ro'yxati manba modulida boshqariladi, xodim o'zini o'zi qo'sha
    olmaydi."""
    row = await db.scalar(
        select(Acknowledgement).where(
            Acknowledgement.user_id == user_id,
            Acknowledgement.object_type == object_type,
            Acknowledgement.object_id == object_id,
            Acknowledgement.version == version,
        )
    )
    if row is None:
        return None
    if row.acknowledged_at is None:
        row.acknowledged_at = datetime.utcnow()
        await db.commit()
    return row


async def pending_for(db: AsyncSession, user_id: int) -> list[PendingItem]:
    """Xodim tanishishi kerak bo'lgan bandlar.

    ⚠️ FAQAT ENG YANGI VERSIYA. Yo'riqnoma ikki marta yangilangan va
    xodim ikkalasini ham o'tkazib yuborgan bo'lsa, unga IKKITA emas,
    BITTA band ko'rinadi — eskisini o'qishning ma'nosi yo'q, u
    almashtirilgan."""
    rows = list(
        await db.scalars(
            select(Acknowledgement).where(
                Acknowledgement.user_id == user_id,
                Acknowledgement.acknowledged_at.is_(None),
            )
        )
    )
    #  Obyekt bo'yicha eng katta versiyani qoldiramiz.
    eng_yangi: dict[tuple[str, int], Acknowledgement] = {}
    for r in rows:
        kalit = (r.object_type, r.object_id)
        bor = eng_yangi.get(kalit)
        if bor is None or r.version > bor.version:
            eng_yangi[kalit] = r

    return sorted(
        (
            PendingItem(
                id=r.id,
                object_type=r.object_type,
                object_type_label=ACK_OBJECT_LABELS.get(r.object_type, r.object_type),
                object_id=r.object_id,
                version=r.version,
                title=r.title,
                link=r.link,
                requested_at=r.requested_at,
            )
            for r in eng_yangi.values()
        ),
        key=lambda i: i.requested_at,
    )


async def who_read(
    db: AsyncSession, *, object_type: str, object_id: int, version: int | None = None
) -> list[ReaderRow]:
    """Kim o'qigan, kim o'qimagan (rahbar paneli uchun).

    `version` berilmasa ENG SO'NGGI versiya olinadi — rahbarni odatda
    «hozirgi matn bilan kim tanishdi?» qiziqtiradi."""
    if version is None:
        version = await db.scalar(
            select(func.max(Acknowledgement.version)).where(
                Acknowledgement.object_type == object_type,
                Acknowledgement.object_id == object_id,
            )
        )
        if version is None:
            return []

    rows = list(
        await db.scalars(
            select(Acknowledgement).where(
                Acknowledgement.object_type == object_type,
                Acknowledgement.object_id == object_id,
                Acknowledgement.version == version,
            )
        )
    )
    ismlar = {u.id: u.full_name for u in await db.scalars(select(User))}
    return sorted(
        (
            ReaderRow(
                user_id=r.user_id,
                user_name=ismlar.get(r.user_id, "—"),
                version=r.version,
                acknowledged_at=r.acknowledged_at,
            )
            for r in rows
        ),
        #  O'qimaganlar TEPADA — rahbarga aynan ular kerak.
        key=lambda r: (r.acknowledged_at is not None, r.user_name),
    )


async def stats(
    db: AsyncSession, *, object_type: str, object_id: int, version: int | None = None
) -> dict:
    """Qisqacha: nechtadan nechtasi tanishgan."""
    qatorlar = await who_read(db, object_type=object_type, object_id=object_id, version=version)
    oqigan = sum(1 for r in qatorlar if r.acknowledged_at is not None)
    return {
        "total": len(qatorlar),
        "read": oqigan,
        "pending": len(qatorlar) - oqigan,
        "version": qatorlar[0].version if qatorlar else None,
    }


# ─────────────────────────────────────────────────────────────
# ESLATMA (yangi TZ 3.16 / S-42)
# ─────────────────────────────────────────────────────────────

#  ⚠️ IKKI SON — MODULNING BUTUN SIYOSATI.
#  `ESLATMA_KUNI` — so'ralgandan keyin necha kun jim turamiz va
#  eslatmalar orasida necha kun kutamiz.
#  `MAX_ESLATMA` — undan keyin bot JIM BO'LADI va band HR ro'yxatiga
#  tushadi.
#
#  NEGA CHEKLANGAN: cheksiz eslatma «shovqin»ga aylanadi va xodim
#  botni butunlay o'chirib qo'yadi — shundan keyin unga BOSHQA hech
#  qanday xabar (kechikish, oylik, vazifa) ham yetib bormaydi. Ya'ni
#  cheksiz eslatma bitta modulni emas, BUTUN tizimni buzadi.
#  Uch martadan keyin masala texnik emas: HR odam bilan gaplashishi
#  kerak.
ESLATMA_KUNI = 3
MAX_ESLATMA = 3


@dataclass(frozen=True)
class ReminderRow:
    """Eslatma yuborilishi kerak bo'lgan bitta band."""

    id: int
    user_id: int
    object_type: str
    object_id: int
    version: int
    title: str | None
    link: str | None
    reminder_count: int


async def due_for_reminder(
    db: AsyncSession,
    *,
    object_type: str,
    now: datetime | None = None,
) -> list[ReminderRow]:
    """Eslatma vaqti kelgan bandlar.

    Shart: tanishilmagan · so'ralganiga `ESLATMA_KUNI` kun bo'lgan ·
    oxirgi eslatmadan beri ham shuncha o'tgan · sanoq `MAX_ESLATMA`
    dan kichik.

    ⚠️ FAQAT ENG YANGI VERSIYA. Yo'riqnoma ikki marta yangilangan
    bo'lsa, eski versiya uchun eslatma yuborish mantiqsiz — u
    almashtirilgan (`pending_for` bilan bir xil qoida)."""
    hozir = now or datetime.utcnow()
    chegara = hozir - timedelta(days=ESLATMA_KUNI)

    rows = list(
        await db.scalars(
            select(Acknowledgement).where(
                Acknowledgement.object_type == object_type,
                Acknowledgement.acknowledged_at.is_(None),
                Acknowledgement.reminder_count < MAX_ESLATMA,
                Acknowledgement.requested_at <= chegara,
            )
        )
    )
    #  Obyekt bo'yicha eng katta versiyani qoldiramiz.
    eng_yangi: dict[tuple[int, str, int], Acknowledgement] = {}
    for r in rows:
        kalit = (r.user_id, r.object_type, r.object_id)
        bor = eng_yangi.get(kalit)
        if bor is None or r.version > bor.version:
            eng_yangi[kalit] = r

    natija = []
    for r in eng_yangi.values():
        if r.last_reminded_at is not None and r.last_reminded_at > chegara:
            continue  # hali erta
        natija.append(
            ReminderRow(
                id=r.id,
                user_id=r.user_id,
                object_type=r.object_type,
                object_id=r.object_id,
                version=r.version,
                title=r.title,
                link=r.link,
                reminder_count=r.reminder_count,
            )
        )
    return sorted(natija, key=lambda x: x.id)


async def mark_reminded(
    db: AsyncSession, ids: list[int], *, now: datetime | None = None
) -> int:
    """Eslatma YUBORILGANDAN KEYIN sanoqni oshiradi.

    ⚠️ Chaqiruvchi COMMIT qiladi. Sanoq xabar HAQIQATAN yuborilgandan
    keyin oshirilishi kerak — aks holda yuborish yiqilsa xodim
    eslatmani olmay turib «eslatilgan» bo'lib qolardi."""
    if not ids:
        return 0
    hozir = now or datetime.utcnow()
    for row in await db.scalars(
        select(Acknowledgement).where(Acknowledgement.id.in_(ids))
    ):
        row.reminder_count = (row.reminder_count or 0) + 1
        row.last_reminded_at = hozir
    await db.flush()
    return len(ids)


async def overview(db: AsyncSession, *, object_type: str) -> list[dict]:
    """HR paneli: obyekt bo'yicha kim tanishgan / kim yo'q.

    ⚠️ FAQAT ENG SO'NGGI VERSIYA hisoblanadi — HR ni «hozirgi matn
    bilan kim tanishdi?» qiziqtiradi, eski versiyalar tarix.

    ⚠️ `exhausted` — bot uch marta eslatib bo'lgan va endi JIM.
    Aynan shu odamlar bilan HR gaplashishi kerak; ro'yxatning butun
    ma'nosi shu."""
    rows = list(
        await db.scalars(
            select(Acknowledgement).where(Acknowledgement.object_type == object_type)
        )
    )
    if not rows:
        return []

    #  Obyekt bo'yicha eng katta versiya.
    eng_yangi: dict[int, int] = {}
    for r in rows:
        if r.version > eng_yangi.get(r.object_id, 0):
            eng_yangi[r.object_id] = r.version

    ismlar = {u.id: u.full_name for u in await db.scalars(select(User))}
    yigma: dict[int, dict] = {}
    for r in rows:
        if r.version != eng_yangi.get(r.object_id):
            continue
        band = yigma.setdefault(
            r.object_id,
            {
                "object_id": r.object_id,
                "object_type": r.object_type,
                "version": r.version,
                "title": r.title,
                "read": [],
                "pending": [],
            },
        )
        odam = {
            "user_id": r.user_id,
            "full_name": ismlar.get(r.user_id, "—"),
            "acknowledged_at": r.acknowledged_at,
            "reminder_count": r.reminder_count or 0,
            #  Bot jim bo'ldi — endi HR ning ishi.
            "exhausted": (r.reminder_count or 0) >= MAX_ESLATMA,
        }
        band["read" if r.acknowledged_at else "pending"].append(odam)

    for band in yigma.values():
        band["read"].sort(key=lambda x: x["full_name"])
        #  Bot jim bo'lganlar TEPADA — HR aynan ularni qidiradi.
        band["pending"].sort(key=lambda x: (not x["exhausted"], x["full_name"]))
        band["total"] = len(band["read"]) + len(band["pending"])
        band["exhausted_count"] = sum(1 for x in band["pending"] if x["exhausted"])
    return sorted(yigma.values(), key=lambda b: (-b["exhausted_count"], b["object_id"]))
