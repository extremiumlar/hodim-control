"""Ichki e'lonlar (yangi TZ 3.12 / S-21).

E'lonlar hozir umumiy Telegram guruhida yo'qoladi — yangi xabarlar ostida
qolib ketadi va «men ko'rmadim» degan javobni tekshirib bo'lmaydi.

⚠️ QAMROV — FILTR, BEZAK EMAS (TZ qabul mezoni)
Qamrovga kirmagan xodimga e'lon UMUMAN ko'rinmaydi: sotuv bo'limiga
aytilgan gap prorabga ko'rinmasligi kerak. Shuning uchun tekshiruv
SERVERDA va bitta funksiyada (`visible_to`) — mijoz filtriga tayanish
maxfiylikni buzardi.

⚠️ KUNLIK LIMIT
Cheklovsiz tizim e'lon spamiga aylanadi: kuniga o'nta xabar kelsa xodim
ularni o'qimay yopib qo'yadi va MUHIM e'lon ham shu taqdirni ko'radi.
Limit `announcement_config.daily_limit` da (default 3).
"""
from __future__ import annotations

from datetime import date, datetime, time

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import (
    ACK_OBJECT_LABELS,  # noqa: F401  (turlar ro'yxati hujjatlashtirish uchun)
    AckObjectType,
    Announcement,
    AnnouncementAudience,
    AnnouncementConfig,
    User,
)


async def get_config(db: AsyncSession) -> AnnouncementConfig:
    cfg = await db.get(AnnouncementConfig, 1)
    if cfg is None:
        cfg = AnnouncementConfig(id=1)
        db.add(cfg)
        await db.commit()
        await db.refresh(cfg)
    return cfg


async def sent_today(db: AsyncSession, day: date) -> int:
    """Bugun nechta e'lon yuborilgan (o'chirilganlari ham sanaladi).

    O'CHIRILGANLARI HAM: aks holda limitni chetlab o'tish oson bo'lardi
    — e'lon yuborib, o'chirib, yana yuborish. Xodimlar xabarni allaqachon
    olgan, o'chirish ularning e'tiborini qaytarmaydi."""
    return (
        await db.scalar(
            select(func.count())
            .select_from(Announcement)
            .where(
                Announcement.created_at >= datetime.combine(day, time.min),
                Announcement.created_at <= datetime.combine(day, time.max),
            )
        )
    ) or 0


async def audience_user_ids(
    db: AsyncSession, audience: str, scope_ids: list | None
) -> list[int]:
    """Qamrovga kiradigan FAOL xodimlar.

    ⚠️ Bo'sh `scope_ids` «hamma» degani EMAS — hech kim. Chaqiruvchi
    (router) uni oldindan rad etadi, bu yerda esa jimgina bo'sh ro'yxat
    qaytadi: e'lon yaratilib, hech kimga ko'rinmay qolishi mumkin emas."""
    q = select(User).where(User.is_active.is_(True))
    rows = list(await db.scalars(q))

    if audience == AnnouncementAudience.all.value:
        return [u.id for u in rows]
    if not scope_ids:
        return []
    if audience == AnnouncementAudience.roles.value:
        tanlangan = {str(x) for x in scope_ids}
        return [u.id for u in rows if u.role in tanlangan]
    if audience == AnnouncementAudience.positions.value:
        tanlangan = {int(x) for x in scope_ids}
        return [u.id for u in rows if u.position_id in tanlangan]
    if audience == AnnouncementAudience.users.value:
        tanlangan = {int(x) for x in scope_ids}
        return [u.id for u in rows if u.id in tanlangan]
    return []


async def visible_to(db: AsyncSession, user: User) -> list[Announcement]:
    """Shu xodim KO'RADIGAN e'lonlar.

    Qamrov tekshiruvi shu yerda — yagona joyda. Web, bot va kabinet
    shundan foydalanadi, ya'ni uchtasida uch xil qoida bo'lishi mumkin
    emas."""
    rows = list(
        await db.scalars(
            select(Announcement)
            .where(Announcement.deleted_at.is_(None))
            .order_by(Announcement.created_at.desc())
        )
    )
    out: list[Announcement] = []
    for a in rows:
        if a.audience == AnnouncementAudience.all.value:
            out.append(a)
            continue
        ids = a.scope_ids or []
        if a.audience == AnnouncementAudience.roles.value:
            if user.role in {str(x) for x in ids}:
                out.append(a)
        elif a.audience == AnnouncementAudience.positions.value:
            if user.position_id is not None and user.position_id in {int(x) for x in ids}:
                out.append(a)
        elif a.audience == AnnouncementAudience.users.value:
            if user.id in {int(x) for x in ids}:
                out.append(a)
    return out


async def publish(
    db: AsyncSession,
    *,
    announcement: Announcement,
    author_id: int | None,
) -> int:
    """E'lonni tarqatadi: muhim bo'lsa «Tanishdim» so'raladi.

    Qaytaradi: qamrovdagi xodimlar soni.

    ⚠️ Chaqiruvchi COMMIT qiladi — e'lon yaratish va tanishish so'rovi
    BITTA tranzaksiyada bo'lishi kerak, aks holda «e'lon bor, lekin hech
    kimdan so'ralmagan» holati paydo bo'lardi."""
    from api.services.acknowledgements import request_ack

    kimga = await audience_user_ids(db, announcement.audience, announcement.scope_ids)
    if announcement.important and kimga:
        await request_ack(
            db,
            object_type=AckObjectType.announcement.value,
            object_id=announcement.id,
            version=announcement.version,
            user_ids=kimga,
            title=announcement.title,
            link="/me/announcements",
            requested_by=author_id,
        )
    return len(kimga)
