"""Ichki e'lonlar — API (yangi TZ 3.12 / S-21).

Qamrov tekshiruvi `api/services/announcements.py::visible_to` da — yagona
joyda. Bu yerdagi endpointlar faqat shu funksiyaga tayanadi.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user, get_db, require_roles
from api.services import announcements as svc
from api.timeutil import today_local
from db.models import (
    AckObjectType,
    Announcement,
    AnnouncementAudience,
    Position,
    Role,
    User,
)

router = APIRouter(prefix="/announcements", tags=["announcements"])

#  E'lon yozish — rahbarlar. ROP ham yozadi (o'z jamoasiga xabar).
_AUTHOR = (Role.hr.value, Role.boss.value, Role.dasturchi.value, Role.rop.value)


class AnnouncementOut(BaseModel):
    id: int
    title: str
    body: str
    audience: str
    scope_ids: list | None
    important: bool
    file_id: str | None
    file_type: str | None
    version: int
    author_id: int | None
    author_name: str | None
    created_at: datetime
    #  Xodim ko'rinishida: shu e'lon bilan tanishganmi (muhim bo'lsa).
    acknowledged: bool | None = None


class AnnouncementIn(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    body: str = Field(min_length=3, max_length=5000)
    audience: str = AnnouncementAudience.all.value
    scope_ids: list | None = None
    important: bool = False
    file_id: str | None = Field(default=None, max_length=512)
    file_type: str | None = None


class ConfigIn(BaseModel):
    daily_limit: int = Field(ge=1, le=50)


def _out(
    a: Announcement,
    ismlar: dict[int, str],
    acked: set[tuple[int, int]] | None = None,
) -> AnnouncementOut:
    return AnnouncementOut(
        id=a.id,
        title=a.title,
        body=a.body,
        audience=a.audience,
        scope_ids=a.scope_ids,
        important=a.important,
        file_id=a.file_id,
        file_type=a.file_type,
        version=a.version,
        author_id=a.author_id,
        author_name=ismlar.get(a.author_id) if a.author_id else None,
        created_at=a.created_at,
        #  ⚠️ VERSIYA BILAN. Faqat `a.id` bo'yicha tekshirilsa, matn
        #  tahrirlangach (v2) xodim hamon «tanishgan» ko'rinardi va S-20
        #  ning butun mazmuni yo'qolardi: u ESKI matnga rozi bo'lgan.
        acknowledged=((a.id, a.version) in acked)
        if (acked is not None and a.important)
        else None,
    )


@router.get("/me", response_model=list[AnnouncementOut])
async def my_announcements(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[AnnouncementOut]:
    """Men ko'radigan e'lonlar.

    ⚠️ Qamrovga kirmagan e'lon UMUMAN kelmaydi — bu maxfiylik talabi,
    interfeys bezagi emas."""
    from db.models import Acknowledgement

    rows = await svc.visible_to(db, user)
    ismlar = {u.id: u.full_name for u in await db.scalars(select(User))}
    acked = {
        (oid, ver)
        for oid, ver in (
            await db.execute(
                select(Acknowledgement.object_id, Acknowledgement.version).where(
                    Acknowledgement.user_id == user.id,
                    Acknowledgement.object_type == AckObjectType.announcement.value,
                    Acknowledgement.acknowledged_at.isnot(None),
                )
            )
        ).all()
    }
    return [_out(a, ismlar, acked) for a in rows]


@router.get("", response_model=list[AnnouncementOut])
async def list_announcements(
    _actor: User = Depends(require_roles(*_AUTHOR)),
    db: AsyncSession = Depends(get_db),
) -> list[AnnouncementOut]:
    """Rahbar ko'rinishi — hamma e'lon (qamrovdan qat'i nazar)."""
    rows = list(
        await db.scalars(
            select(Announcement)
            .where(Announcement.deleted_at.is_(None))
            .order_by(Announcement.created_at.desc())
        )
    )
    ismlar = {u.id: u.full_name for u in await db.scalars(select(User))}
    return [_out(a, ismlar) for a in rows]


@router.get("/quota")
async def quota(
    _actor: User = Depends(require_roles(*_AUTHOR)), db: AsyncSession = Depends(get_db)
) -> dict:
    """Bugun yana nechta e'lon yuborish mumkin."""
    cfg = await svc.get_config(db)
    yuborilgan = await svc.sent_today(db, today_local())
    return {
        "daily_limit": cfg.daily_limit,
        "sent_today": yuborilgan,
        "left": max(0, cfg.daily_limit - yuborilgan),
    }


@router.post("", status_code=status.HTTP_201_CREATED)
async def add_announcement(
    payload: AnnouncementIn,
    actor: User = Depends(require_roles(*_AUTHOR)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if payload.audience not in {a.value for a in AnnouncementAudience}:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Noma'lum qamrov")
    if payload.audience != AnnouncementAudience.all.value and not payload.scope_ids:
        #  Bo'sh ro'yxat «hamma» EMAS — hech kim. E'lon jimgina
        #  yo'qolmasin, muallif xatosini darhol bilsin.
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Qamrov tanlangan, lekin ro'yxat bo'sh — e'lon hech kimga ko'rinmaydi",
        )
    if payload.audience == AnnouncementAudience.roles.value:
        yaroqli = {r.value for r in Role}
        yomon = [x for x in payload.scope_ids or [] if str(x) not in yaroqli]
        if yomon:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Noma'lum rol: {yomon}")
    if payload.audience == AnnouncementAudience.positions.value:
        bor = {p.id for p in await db.scalars(select(Position))}
        yomon = [x for x in payload.scope_ids or [] if int(x) not in bor]
        if yomon:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Lavozim topilmadi: {yomon}")

    # ── KUNLIK LIMIT ──
    cfg = await svc.get_config(db)
    yuborilgan = await svc.sent_today(db, today_local())
    if yuborilgan >= cfg.daily_limit:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Bugungi e'lon chegarasi to'ldi ({cfg.daily_limit} ta). "
            "Ertaga yuboring yoki chegarani sozlamadan oshiring — "
            "kuniga ko'p e'lon kelsa xodimlar ularni o'qimay qo'yadi.",
        )

    a = Announcement(
        title=payload.title.strip(),
        body=payload.body.strip(),
        audience=payload.audience,
        scope_ids=payload.scope_ids,
        important=payload.important,
        file_id=payload.file_id,
        file_type=payload.file_type,
        author_id=actor.id,
    )
    db.add(a)
    await db.flush()
    qamrov = await svc.publish(db, announcement=a, author_id=actor.id)
    await db.commit()
    return {
        "id": a.id,
        "audience_size": qamrov,
        "ack_requested": bool(a.important and qamrov),
        "left_today": max(0, cfg.daily_limit - yuborilgan - 1),
    }


#  ⚠️ `/config` marshrutlari `/{ann_id}` dan OLDIN turishi SHART:
#  FastAPI e'lon tartibida solishtiradi va «config» so'zi `{ann_id}`
#  ga tushib, butun son sifatida o'qilmoqchi bo'lardi (422).
@router.get("/config")
async def read_config(
    _actor: User = Depends(require_roles(*_AUTHOR)), db: AsyncSession = Depends(get_db)
) -> dict:
    cfg = await svc.get_config(db)
    return {"daily_limit": cfg.daily_limit}


@router.put("/config")
async def write_config(
    payload: ConfigIn,
    _actor: User = Depends(
        require_roles(Role.hr.value, Role.boss.value, Role.dasturchi.value)
    ),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Chegarani ROP o'zgartira olmaydi — u ham e'lon yozadi, ya'ni o'z
    cheklovini o'zi ko'tarib qo'yishi mumkin bo'lardi."""
    cfg = await svc.get_config(db)
    cfg.daily_limit = payload.daily_limit
    await db.commit()
    return {"daily_limit": cfg.daily_limit}


@router.put("/{ann_id}")
async def edit_announcement(
    ann_id: int,
    payload: AnnouncementIn,
    actor: User = Depends(require_roles(*_AUTHOR)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Matn tahrirlansa VERSIYA oshadi va tanishuv QAYTA so'raladi.

    NEGA: xodim eski matnga rozi bo'lgan. Yangisi boshqa narsa aytayotgan
    bo'lsa, eski «Tanishdim» hech nimani isbotlamaydi (S-20 qoidasi)."""
    a = await db.get(Announcement, ann_id)
    if a is None or a.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Topilmadi")

    matn_ozgardi = a.title != payload.title.strip() or a.body != payload.body.strip()
    a.title = payload.title.strip()
    a.body = payload.body.strip()
    a.audience = payload.audience
    a.scope_ids = payload.scope_ids
    a.important = payload.important
    if matn_ozgardi:
        a.version += 1
    await db.flush()
    if matn_ozgardi or payload.important:
        await svc.publish(db, announcement=a, author_id=actor.id)
    await db.commit()
    return {"ok": True, "version": a.version, "reacked": matn_ozgardi}


@router.delete("/{ann_id}")
async def delete_announcement(
    ann_id: int,
    _actor: User = Depends(require_roles(*_AUTHOR)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Yumshoq o'chirish — tanishuv qaydi tarixda qolishi kerak."""
    a = await db.get(Announcement, ann_id)
    if a is None or a.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Topilmadi")
    a.deleted_at = datetime.utcnow()
    await db.commit()
    return {"ok": True}

