"""Texnika xavfsizligi instruktaji — mantiq (yangi TZ 3.6 / S-48).

═══════════════════════════════════════════════════════════════
⚠️ QOG'OZ JURNAL O'RNINI BOSMAYDI
═══════════════════════════════════════════════════════════════
Mehnat muhofazasi instruktaji jurnali — QONUN talab qiladigan
hujjat va u xodimning QO'L QO'YISHI bilan rasmiylashtiriladi.
Botdagi «Tanishdim» tugmasi buni ALMASHTIRMAYDI. Bu modul
QO'SHIMCHA nazorat vositasi: kim tanishgan, kim yo'q, qaysi
instruktaj muddati o'tgan. Batafsil izoh va HR ga ko'rsatiladigan
matn — `db/models.py::PAPER_JOURNAL_WARNING`.

═══════════════════════════════════════════════════════════════
⚠️ UCHTA MEXANIZM QAYTA ISHLATILADI, YANGISI QURILMAYDI
═══════════════════════════════════════════════════════════════
1. QATNASHCHILAR VA IMZOLAR — S-20 ning umumiy
   `acknowledgements` jadvali (`object_type="briefing"`). Buning
   yon foydasi katta: tanishuv ESLATMASI (S-42) bu turga
   o'z-o'zidan ishlaydi va HR paneli allaqachon tayyor.

2. MATERIAL — o'quv paneli (3.1). Matn/video/hujjat kursning O'Z
   materiallarida; bu yerda faqat `course_id`.

3. TAKRORIY MUDDAT — `deadlines` (S-12). Eslatmani `deadline_tick`
   (S-13) yuboradi: u takrorlanishni o'zi to'sadi va bir kunlik
   bandlarni birlashtiradi.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import (
    ACK_OBJECT_LABELS,
    AckObjectType,
    Acknowledgement,
    BRIEFING_KIND_LABELS,
    BriefingKind,
    Deadline,
    DeadlineKind,
    DeadlineStatus,
    SafetyBriefing,
    User,
)

ACK_TYPE = AckObjectType.briefing.value

#  Instruktaj matni bir marta beriladi va o'zgarmaydi, ya'ni
#  versiyalash kerak emas — S-20 mexanizmi versiyani talab
#  qilgani uchun doimiy `1`.
ACK_VERSION = 1

#  ⚠️ TAKRORIY INSTRUKTAJ DAVRI — mehnat muhofazasi qoidasi
#  bo'yicha odatda 6 oy. TZ 3.6 ham shuni ko'rsatadi (S-49:
#  «har 6 oyda takroriy instruktaj eslatmasi»).
DEFAULT_REPEAT_MONTHS = 6

#  Oyni kunga aylantirish. Kalendar oy o'zgaruvchan, lekin muddat
#  eslatmasi uchun bu aniqlik yetarli — bir-ikki kun farq
#  instruktaj muddatida ahamiyatsiz.
_DAYS_IN_MONTH = 30


def alive() -> Select:
    """Instruktajlarni o'qishning YAGONA to'g'ri yo'li.

    ⚠️ To'g'ridan-to'g'ri `select(SafetyBriefing)` yozilsa
    o'chirilgan qator ham qaytardi va u jurnalda ko'rinardi."""
    return select(SafetyBriefing).where(SafetyBriefing.deleted_at.is_(None))


def kind_label(value: str) -> str:
    return BRIEFING_KIND_LABELS.get(value, value)


async def create(
    db: AsyncSession,
    *,
    kind: str,
    title: str,
    held_on: date,
    user_ids: list[int],
    conducted_by: int | None = None,
    course_id: int | None = None,
    repeat_months: int | None = None,
    note: str | None = None,
    created_by: int | None = None,
) -> SafetyBriefing:
    """Instruktaj yozuvi + qatnashchilardan tanishish so'rovi.

    ⚠️ IKKALASI BITTA TRANZAKSIYADA (chaqiruvchi COMMIT qiladi).
    Aks holda «instruktaj bor, lekin hech kimdan so'ralmagan»
    holati paydo bo'lardi — S-20 ning o'z qoidasi.

    Xatolar `ValueError` bilan."""
    if kind not in BRIEFING_KIND_LABELS:
        raise ValueError(f"Noma'lum instruktaj turi: {kind}")
    if not user_ids:
        raise ValueError("Kamida bitta qatnashchi tanlanishi kerak")

    row = SafetyBriefing(
        kind=kind,
        title=title.strip(),
        held_on=held_on,
        conducted_by=conducted_by,
        course_id=course_id,
        repeat_months=repeat_months,
        note=(note or "").strip() or None,
        created_by=created_by,
    )
    db.add(row)
    await db.flush()

    from api.services import acknowledgements as ack

    await ack.request_ack(
        db,
        object_type=ACK_TYPE,
        object_id=row.id,
        version=ACK_VERSION,
        user_ids=user_ids,
        title=f"{kind_label(kind)} — {row.title}",
        link="/me/briefings",
        requested_by=created_by,
    )
    await _schedule_repeat(db, row, user_ids, created_by)
    return row


async def _schedule_repeat(
    db: AsyncSession,
    row: SafetyBriefing,
    user_ids: list[int],
    created_by: int | None,
) -> int:
    """Takroriy instruktaj muddatini `deadlines` ga yozadi.

    ⚠️ MUDDAT HAR XODIMGA ALOHIDA. `deadlines` moduli xodim
    bo'yicha ishlaydi (kim uchun muddat kelyapti degan savolga
    javob beradi) va bitta umumiy qator bilan «kimga eslatamiz?»
    degan savolga javob bo'lmasdi.

    ⚠️ `repeat_months` bo'sh bo'lsa muddat YARATILMAYDI: kirish
    instruktaji bir marta o'tkaziladi va uni takrorlash uchun
    eslatma yuborish noto'g'ri bo'lardi.

    ⚠️ `deadlines.create` ning O'ZI commit qiladi — bu yerda
    qo'shimcha commit yo'q."""
    if not row.repeat_months or row.repeat_months <= 0:
        return 0
    from api.services import deadlines as dsvc

    muddat = row.held_on + timedelta(days=row.repeat_months * _DAYS_IN_MONTH)
    n = 0
    for uid in user_ids:
        await dsvc.create(
            db,
            user_id=uid,
            kind=DeadlineKind.safety_briefing.value,
            due_date=muddat,
            note=f"Takroriy instruktaj: {row.title}",
            created_by=created_by,
        )
        n += 1
    return n


async def participants(db: AsyncSession, briefing_id: int) -> list[dict]:
    """Kim tanishgan, kim yo'q.

    ⚠️ Manba — `acknowledgements`, bu yerda NUSXA saqlanmaydi."""
    rows = list(
        await db.scalars(
            select(Acknowledgement).where(
                Acknowledgement.object_type == ACK_TYPE,
                Acknowledgement.object_id == briefing_id,
            )
        )
    )
    ismlar = {u.id: u.full_name for u in await db.scalars(select(User))}
    return sorted(
        (
            {
                "user_id": r.user_id,
                "full_name": ismlar.get(r.user_id, "—"),
                "acknowledged_at": r.acknowledged_at,
                "reminder_count": r.reminder_count or 0,
            }
            for r in rows
        ),
        #  Tanishmaganlar TEPADA — HR aynan ularni qidiradi.
        key=lambda x: (x["acknowledged_at"] is not None, x["full_name"]),
    )


async def detail(db: AsyncSession, row: SafetyBriefing) -> dict:
    qatnashchilar = await participants(db, row.id)
    tanishgan = sum(1 for p in qatnashchilar if p["acknowledged_at"])
    return {
        "id": row.id,
        "kind": row.kind,
        "kind_label": kind_label(row.kind),
        "title": row.title,
        "held_on": row.held_on,
        "conducted_by": row.conducted_by,
        "course_id": row.course_id,
        "repeat_months": row.repeat_months,
        "note": row.note,
        "total": len(qatnashchilar),
        "read": tanishgan,
        "pending": len(qatnashchilar) - tanishgan,
        "participants": qatnashchilar,
    }


async def listing(db: AsyncSession, limit: int = 100) -> list[dict]:
    """Jurnal — yangisidan eskisiga."""
    rows = list(
        await db.scalars(
            alive().order_by(SafetyBriefing.held_on.desc(), SafetyBriefing.id.desc())
            .limit(limit)
        )
    )
    natija = []
    for r in rows:
        band = await detail(db, r)
        band.pop("participants", None)  # ro'yxat sahifasiga kerak emas
        natija.append(band)
    return natija


async def for_user(db: AsyncSession, user_id: int) -> list[dict]:
    """Xodimning instruktajlari — tanishgani ham, kutayotgani ham."""
    izlar = {
        r.object_id: r
        for r in await db.scalars(
            select(Acknowledgement).where(
                Acknowledgement.object_type == ACK_TYPE,
                Acknowledgement.user_id == user_id,
            )
        )
    }
    if not izlar:
        return []
    rows = list(
        await db.scalars(
            alive()
            .where(SafetyBriefing.id.in_(list(izlar)))
            .order_by(SafetyBriefing.held_on.desc())
        )
    )
    return [
        {
            "id": r.id,
            "kind": r.kind,
            "kind_label": kind_label(r.kind),
            "title": r.title,
            "held_on": r.held_on,
            "course_id": r.course_id,
            "note": r.note,
            "acknowledged_at": izlar[r.id].acknowledged_at,
            "acknowledged": izlar[r.id].acknowledged_at is not None,
        }
        for r in rows
    ]


async def acknowledge(db: AsyncSession, *, user_id: int, briefing_id: int) -> dict:
    """Xodim «Tanishdim» bosdi.

    ⚠️ S-20 ning `mark_ack` i chaqiriladi — u IDEMPOTENT va
    so'ralmagan bandni tasdiqlamaydi. Ya'ni xodim o'zini
    instruktaj ro'yxatiga qo'sha olmaydi."""
    from api.services import acknowledgements as ack

    row = await ack.mark_ack(
        db,
        user_id=user_id,
        object_type=ACK_TYPE,
        object_id=briefing_id,
        version=ACK_VERSION,
    )
    if row is None:
        raise ValueError("Bu instruktaj sizdan so'ralmagan")
    #  Takroriy muddat yopiladi — xodim tanishdi, eslatma
    #  kelavermasin.
    await _close_deadline(db, user_id, briefing_id)
    return {"ok": True, "acknowledged_at": row.acknowledged_at}


async def _close_deadline(db: AsyncSession, user_id: int, briefing_id: int) -> bool:
    """Shu instruktajga bog'langan OCHIQ muddatni yopadi.

    ⚠️ Bog'lanish `note` MATNI bo'yicha: `deadlines.create`
    manba id sini saqlamaydi (qo'lda kiritilgan muddatlar uchun
    mo'ljallangan). Matn instruktaj sarlavhasini o'z ichiga oladi,
    ya'ni moslik aniq."""
    row = await db.get(SafetyBriefing, briefing_id)
    if row is None:
        return False
    izlanayotgan = f"Takroriy instruktaj: {row.title}"
    muddat = await db.scalar(
        select(Deadline).where(
            Deadline.user_id == user_id,
            Deadline.kind == DeadlineKind.safety_briefing.value,
            Deadline.status == DeadlineStatus.open.value,
            Deadline.note == izlanayotgan,
        )
    )
    if muddat is None:
        return False
    muddat.status = DeadlineStatus.done.value
    await db.flush()
    return True


# ─────────────────────────────────────────────────────────────
# HISOBOT VA KADR AUDITI (yangi TZ 3.6 / S-49)
# ─────────────────────────────────────────────────────────────


async def overdue(db: AsyncSession, today: date | None = None) -> list[dict]:
    """Muddati O'TGAN takroriy instruktajlar.

    ⚠️ MANBA — `deadlines` (S-12), bu yerda qayta hisoblanmaydi.
    Muddat instruktaj yaratilganda o'sha yerga yozilgan va xodim
    tanishgach yopiladi; ya'ni OCHIQ va sanasi o'tgan qator
    aynan «muddati o'tgan instruktaj» degani. Ikkinchi hisob
    qilsak, ikkita haqiqat paydo bo'lardi."""
    from api.timeutil import today_local

    bugun = today or today_local()
    rows = list(
        await db.scalars(
            select(Deadline).where(
                Deadline.kind == DeadlineKind.safety_briefing.value,
                Deadline.status == DeadlineStatus.open.value,
                Deadline.due_date.isnot(None),
                Deadline.due_date < bugun,
            )
        )
    )
    if not rows:
        return []
    ismlar = {u.id: u.full_name for u in await db.scalars(select(User))}
    natija = [
        {
            "user_id": r.user_id,
            "full_name": ismlar.get(r.user_id, "—"),
            "due_date": r.due_date,
            "days_late": (bugun - r.due_date).days,
            "note": r.note,
        }
        for r in rows
    ]
    #  Eng ko'p kechikkanlar TEPADA — ular eng katta xavf.
    return sorted(natija, key=lambda x: -x["days_late"])


async def audit_rows(db: AsyncSession) -> list[dict]:
    """Kadr auditi so'rovi (TZ 3.30 uchun tayyorlangan).

    ⚠️ TEKSHIRUVCHI SAVOLI SHAKLIDA: «har bir xodim bo'yicha
    qaysi turdagi instruktaj, qachon, tanishganmi». Aynan shu
    kesimda so'raladi va uni jurnal ro'yxatidan qo'lda yig'ish
    uzoq vaqt olardi.

    ⚠️ FAOL xodimlar bo'yicha. Ishdan bo'shaganlar auditda
    so'ralmaydi va ro'yxatni uzaytirib yuborardi."""
    xodimlar = list(
        await db.scalars(
            select(User).where(User.is_active.is_(True)).order_by(User.full_name)
        )
    )
    instruktajlar = {r.id: r for r in await db.scalars(alive())}
    if not instruktajlar:
        return [
            {"user_id": u.id, "full_name": u.full_name, "kinds": {}} for u in xodimlar
        ]

    izlar = list(
        await db.scalars(
            select(Acknowledgement).where(Acknowledgement.object_type == ACK_TYPE)
        )
    )
    #  (xodim, tur) -> eng SO'NGGI instruktaj
    yigma: dict[tuple[int, str], dict] = {}
    for iz in izlar:
        b = instruktajlar.get(iz.object_id)
        if b is None:
            continue
        kalit = (iz.user_id, b.kind)
        bor = yigma.get(kalit)
        if bor is None or b.held_on > bor["held_on"]:
            yigma[kalit] = {
                "briefing_id": b.id,
                "title": b.title,
                "held_on": b.held_on,
                "acknowledged": iz.acknowledged_at is not None,
                "acknowledged_at": iz.acknowledged_at,
            }

    return [
        {
            "user_id": u.id,
            "full_name": u.full_name,
            "kinds": {
                tur: yigma[(u.id, tur)]
                for tur in BRIEFING_KIND_LABELS
                if (u.id, tur) in yigma
            },
            #  Tekshiruvchi birinchi shuni so'raydi: KIRISH
            #  instruktaji bormi. Yo'q bo'lsa bu jiddiy kamchilik.
            "has_intro": (u.id, BriefingKind.intro.value) in yigma,
        }
        for u in xodimlar
    ]


async def report(db: AsyncSession) -> dict:
    """Umumiy hisobot: tanishmaganlar, muddati o'tganlar, audit."""
    kutayotganlar = []
    ismlar = {u.id: u.full_name for u in await db.scalars(select(User))}
    instruktajlar = {r.id: r for r in await db.scalars(alive())}
    for iz in await db.scalars(
        select(Acknowledgement).where(
            Acknowledgement.object_type == ACK_TYPE,
            Acknowledgement.acknowledged_at.is_(None),
        )
    ):
        b = instruktajlar.get(iz.object_id)
        if b is None:
            continue
        kutayotganlar.append(
            {
                "user_id": iz.user_id,
                "full_name": ismlar.get(iz.user_id, "—"),
                "briefing_id": b.id,
                "title": b.title,
                "kind_label": kind_label(b.kind),
                "held_on": b.held_on,
                "reminder_count": iz.reminder_count or 0,
            }
        )
    kutayotganlar.sort(key=lambda x: (x["held_on"], x["full_name"]))

    audit = await audit_rows(db)
    return {
        "pending": kutayotganlar,
        "overdue": await overdue(db),
        "audit": audit,
        "without_intro": [a["full_name"] for a in audit if not a["has_intro"]],
    }
