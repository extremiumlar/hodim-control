"""Tashkiliy tuzilma — mantiq (yangi TZ 3.16 / S-39).

Uch narsa:
  • lavozimlar IERARXIYASI (`positions.parent_position_id`);
  • lavozim YO'RIQNOMASI — versiyalanadi, tahrirlanmaydi;
  • kompaniya profili (missiya, qadriyatlar, maqsadlar).

═══════════════════════════════════════════════════════════════
⚠️ IKKI QAT'IY QOIDA (S-39 qabul mezonlari)
═══════════════════════════════════════════════════════════════
1. IERARXIYA HALQA HOSIL QILMAYDI. Faqat «o'ziga bo'ysunish» emas —
   A→B→C→A kabi uzun halqa ham. Halqa bo'lsa sxema chizilganda
   cheksiz rekursiyaga tushardi va `GET /org-chart` butun saytni osib
   qo'yardi (Passenger'da konkurentlik = 1, ya'ni bitta osilgan so'rov
   HAMMANI to'xtatadi). Tekshiruv `assert_no_cycle` da — YAGONA joyda.

2. YO'RIQNOMA TAHRIRLANMAYDI, YANGI VERSIYA QO'SHILADI. Yo'riqnoma —
   huquqiy hujjat. Xodim «tanishdim» degan bo'lsa (S-20), keyin matn
   jimgina o'zgarsa, u AYNAN NIMAGA rozi bo'lgani noma'lum bo'lardi.
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import CompanyProfile, JobDescription, Position, User

#  Ierarxiya chuqurligi chegarasi. Halqa qo'riqchisi bo'lsa ham bu
#  ikkinchi to'siq: baza qo'lda tahrirlansa (yoki migratsiya xato
#  ma'lumot keltirsa) aylanish cheksiz bo'lib qolmasin.
MAX_DEPTH = 50


async def _positions_map(db: AsyncSession) -> dict[int, Position]:
    return {p.id: p for p in await db.scalars(select(Position))}


async def assert_no_cycle(
    db: AsyncSession, *, position_id: int, parent_id: int | None
) -> None:
    """`position_id` ning otasi `parent_id` bo'lishi MUMKINMI.

    ⚠️ To'liq halqa tekshiruvi, faqat o'ziga bo'ysunish emas. Yangi
    bog'lanish qo'yilgandan KEYINGI holatni tekshiradi: `parent_id`
    dan yuqoriga chiqib, `position_id` ga qaytib kelsak — halqa.

    Xato bo'lsa `ValueError` (chaqiruvchi 400 ga aylantiradi)."""
    if parent_id is None:
        return
    if parent_id == position_id:
        raise ValueError("Lavozim o'ziga bo'ysuna olmaydi")
    xarita = await _positions_map(db)
    if parent_id not in xarita:
        raise ValueError("Ota lavozim topilmadi")

    korilgan: set[int] = set()
    joriy: int | None = parent_id
    qadam = 0
    while joriy is not None:
        if joriy == position_id:
            raise ValueError(
                "Bunday bo'ysunish HALQA hosil qiladi — tuzilma yopiq "
                "aylanaga aylanib qolardi"
            )
        if joriy in korilgan:
            #  Bazada allaqachon halqa bor (qo'lda tahrirlangan).
            #  Yangi bog'lanishni rad etamiz, aks holda u ham qo'shilardi.
            raise ValueError("Tuzilmada allaqachon halqa bor — avval uni tuzating")
        korilgan.add(joriy)
        qadam += 1
        if qadam > MAX_DEPTH:
            raise ValueError(f"Ierarxiya juda chuqur ({MAX_DEPTH} dan ortiq)")
        ota = xarita.get(joriy)
        joriy = ota.parent_position_id if ota is not None else None


async def set_parent(
    db: AsyncSession, *, position: Position, parent_id: int | None
) -> Position:
    await assert_no_cycle(db, position_id=position.id, parent_id=parent_id)
    position.parent_position_id = parent_id
    await db.flush()
    return position


async def chart(db: AsyncSession) -> dict:
    """Sxema uchun TUGUNLAR va BOG'LANISHLAR.

    ⚠️ RASM SERVERDA YARATILMAYDI (TZ 3.16 / S-40) — server faqat
    ma'lumot beradi, chizishni brauzer qiladi. Rasm generatsiyasi
    Passenger ishchisini band qilardi."""
    lavozimlar = list(await db.scalars(select(Position).where(Position.is_active.is_(True))))
    xodimlar = list(await db.scalars(select(User).where(User.is_active.is_(True))))
    sanoq: dict[int, int] = {}
    for u in xodimlar:
        if u.position_id:
            sanoq[u.position_id] = sanoq.get(u.position_id, 0) + 1

    #  Yo'riqnomasi bor lavozimlar (eng so'nggi versiya bo'yicha).
    yoriqnomali = {
        j.position_id
        for j in await db.scalars(select(JobDescription))
    }
    return {
        "nodes": [
            {
                "id": p.id,
                "name": p.name,
                "parent_id": p.parent_position_id,
                "employees": sanoq.get(p.id, 0),
                "has_description": p.id in yoriqnomali,
            }
            for p in lavozimlar
        ],
        #  Bo'shliqlar — TZ 3.16 aniq so'ragan ikki ro'yxat.
        "gaps": {
            "without_description": [
                {"id": p.id, "name": p.name}
                for p in lavozimlar
                if p.id not in yoriqnomali
            ],
            "without_manager": [
                {"id": u.id, "full_name": u.full_name}
                for u in xodimlar
                if u.manager_id is None and u.role == "employee"
            ],
        },
    }


# ─────────────────────────────────────────────────────────────
# YO'RIQNOMA — VERSIYALAR
# ─────────────────────────────────────────────────────────────


async def versions(db: AsyncSession, position_id: int) -> list[JobDescription]:
    """Barcha versiyalar, YANGISIDAN eskisiga."""
    return list(
        await db.scalars(
            select(JobDescription)
            .where(JobDescription.position_id == position_id)
            .order_by(JobDescription.version.desc())
        )
    )


async def current_description(
    db: AsyncSession, position_id: int, on_date: date | None = None
) -> JobDescription | None:
    """Berilgan sanada KUCHDA bo'lgan versiya.

    ⚠️ «Eng katta versiya» EMAS: kelajakdagi sana bilan tayyorlab
    qo'yilgan versiya hali kuchga kirmagan bo'lishi mumkin. Xodim
    hozir amal qiladigan matnni ko'rishi kerak."""
    from api.timeutil import today_local

    kun = on_date or today_local()
    return await db.scalar(
        select(JobDescription)
        .where(
            JobDescription.position_id == position_id,
            JobDescription.effective_from <= kun,
        )
        .order_by(JobDescription.version.desc())
        .limit(1)
    )


async def add_version(
    db: AsyncSession,
    *,
    position_id: int,
    purpose: str | None,
    duties: list,
    rights: list,
    responsibility: list,
    requirements: list,
    effective_from: date | None = None,
    created_by: int | None = None,
) -> JobDescription:
    """YANGI versiya qo'shadi.

    ⚠️ Bu YAGONA yo'l — `UPDATE` funksiyasi ATAYLAB yozilmagan.
    Eski versiya o'z holicha qoladi va unga bog'langan tanishish
    yozuvlari (S-20) kuchini yo'qotmaydi."""
    from api.timeutil import today_local

    oxirgi = await db.scalar(
        select(JobDescription.version)
        .where(JobDescription.position_id == position_id)
        .order_by(JobDescription.version.desc())
        .limit(1)
    )
    row = JobDescription(
        position_id=position_id,
        version=(oxirgi or 0) + 1,
        purpose=(purpose or "").strip() or None,
        duties=[str(x).strip() for x in (duties or []) if str(x).strip()],
        rights=[str(x).strip() for x in (rights or []) if str(x).strip()],
        responsibility=[
            str(x).strip() for x in (responsibility or []) if str(x).strip()
        ],
        requirements=[str(x).strip() for x in (requirements or []) if str(x).strip()],
        effective_from=effective_from or today_local(),
        created_by=created_by,
    )
    db.add(row)
    await db.flush()
    return row


# ─────────────────────────────────────────────────────────────
# KOMPANIYA PROFILI
# ─────────────────────────────────────────────────────────────


async def get_profile(db: AsyncSession) -> CompanyProfile:
    """Yagona qator (id=1) — yo'q bo'lsa yaratiladi."""
    row = await db.get(CompanyProfile, 1)
    if row is None:
        row = CompanyProfile(id=1, values=[], goals=[])
        db.add(row)
        await db.flush()
    return row


async def update_profile(
    db: AsyncSession,
    *,
    mission: str | None = None,
    values: list | None = None,
    goals: list | None = None,
    actor_id: int | None = None,
) -> CompanyProfile:
    """Kompaniya profili — bu YO'RIQNOMA EMAS, versiyalanmaydi.

    Farqi ataylab: missiya huquqiy hujjat emas va unga «tanishdim»
    so'ralmaydi, ya'ni eski matnni saqlash majburiyati yo'q."""
    row = await get_profile(db)
    if mission is not None:
        row.mission = mission.strip() or None
    if values is not None:
        row.values = [str(x).strip() for x in values if str(x).strip()]
    if goals is not None:
        row.goals = [str(x).strip() for x in goals if str(x).strip()]
    row.updated_by = actor_id
    row.updated_at = datetime.utcnow()
    await db.flush()
    return row
