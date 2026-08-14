"""Tabrik videolari — tashrif va shartnoma bo'lganda umumiy guruhga e'lon.

QANDAY ISHLAYDI
---------------
1. CRM'da lid «Tashrif» yoki «Shartnoma qilindi» bosqichiga KO'CHIRILADI.
2. Bu o'zgarish `lead_events` ga yoziladi — ikki manbadan: Uysot webhook'i
   (deyarli darhol) yoki diff-skaner (zaxira). Bu servis O'ZI CRM'ga
   murojaat QILMAYDI — faqat mavjud voqealarni o'qiydi.
3. `announce_pending()` hali e'lon qilinmagan voqealarni topib, guruhga
   rahbar yuklagan videoni «👏 Tabriklash» tugmasi bilan yuboradi.

NEGA ALOHIDA "E'LON QILUVCHI" (voqea yozilgan joyda darhol yubormaymiz):
- voqeani IKKI manba yozadi — yozish joyida yuborsak, ikki marta ketardi;
- `celebration_posts.lead_event_id` UNIQUE — takrorlanishning yagona
  ishonchli to'sig'i shu, va u faqat markazlashgan e'lonchida ishlaydi;
- CRM webhook'i qayta urinsa (Uysot takroriy yuboradi) ham post ko'paymaydi.

XAVFSIZLIK QO'RIQCHILARI
- Faol video bo'lmasa — hech narsa yuborilmaydi (funksiya o'chiq tug'iladi).
- `_LOOKBACK_MINUTES` dan eski voqealar e'lon qilinmaydi: deploy qilingan
  zahoti guruhga o'tgan haftaning 100 ta tashrifi to'kilib ketmasin.
- `_MAX_PER_TICK` — bitta aylanishda yuboriladigan post chegarasi.
"""
import logging
from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.telegram_notify import edit_reply_markup, inline_keyboard, send_file_id, send_message
from api.timeutil import local_range_utc_naive
from crm.config import CRM_UYSOT_CONTRACT_PIPE_STATUS_IDS, CRM_UYSOT_VISIT_PIPE_STATUS_IDS
from db.models import (
    CelebrationClap,
    CelebrationKind,
    CelebrationMedia,
    CelebrationPost,
    LeadEvent,
    MonitoredGroup,
    User,
)

logger = logging.getLogger(__name__)

# Voqea aniqlanganidan keyin qancha vaqt ichida e'lon qilish mantiqiy.
# 6 soat: skaner uzilib qolib kechroq topsa ham tabrik yetib boradi, lekin
# birinchi deploy'da eski tarix guruhga to'kilmaydi.
_LOOKBACK_MINUTES = 6 * 60
_MAX_PER_TICK = 5

_KIND_TITLES = {
    CelebrationKind.visit.value: "🎉 <b>TASHRIF!</b>",
    CelebrationKind.contract.value: "🤝 <b>SHARTNOMA!</b>",
}
_KIND_LABELS = {
    CelebrationKind.visit.value: "Tashrif",
    CelebrationKind.contract.value: "Shartnoma",
}


def _kind_status_ids(kind: str) -> set[int]:
    if kind == CelebrationKind.contract.value:
        return set(CRM_UYSOT_CONTRACT_PIPE_STATUS_IDS)
    return set(CRM_UYSOT_VISIT_PIPE_STATUS_IDS)


def event_kind(ev: LeadEvent) -> str | None:
    """Bu voqea qaysi tabrikka loyiq — yoki umuman loyiq emasmi.

    `first_seen` CHIQARIB TASHLANADI — xuddi tashrif hisobidagi kabi
    (`lead_diff._is_visit_event`): u CRM'dagi hodisa emas, skanerimiz lidni
    endi ko'rgani. Aks holda skaner birinchi marta ishga tushganda guruh
    yuzlab soxta "tashrif" videosiga ko'milib ketardi."""
    if ev.event_type == "first_seen" or ev.to_pipe_status_id is None:
        return None
    for kind in (CelebrationKind.visit.value, CelebrationKind.contract.value):
        ids = _kind_status_ids(kind)
        if ids and ev.to_pipe_status_id in ids and ev.from_pipe_status_id not in ids:
            return kind
    return None


async def active_media(db: AsyncSession, kind: str) -> CelebrationMedia | None:
    return await db.scalar(
        select(CelebrationMedia)
        .where(CelebrationMedia.kind == kind, CelebrationMedia.is_active == True)  # noqa: E712
        .order_by(CelebrationMedia.created_at.desc(), CelebrationMedia.id.desc())
    )


async def media_overview(db: AsyncSession) -> list[dict]:
    """Bot paneli uchun: har tur bo'yicha joriy holat."""
    out = []
    for kind in (CelebrationKind.visit.value, CelebrationKind.contract.value):
        m = await active_media(db, kind)
        sent = await db.scalar(
            select(func.count(CelebrationPost.id)).where(CelebrationPost.kind == kind)
        )
        out.append(
            {
                "kind": kind,
                "label": _KIND_LABELS[kind],
                "configured": m is not None,
                "file_type": m.file_type if m else None,
                "caption": m.caption if m else None,
                "updated_at": m.created_at.isoformat() if m else None,
                "posts_total": sent or 0,
                "stages_configured": bool(_kind_status_ids(kind)),
            }
        )
    return out


async def set_media(
    db: AsyncSession,
    kind: str,
    file_id: str,
    file_type: str,
    caption: str | None,
    actor_id: int | None,
) -> CelebrationMedia:
    """Yangi videoni faol qiladi, eskisini tarixda qoldiradi (o'chirmaydi —
    kerak bo'lsa qaysi video qachon turgani ko'rinib tursin)."""
    for old in await db.scalars(
        select(CelebrationMedia).where(
            CelebrationMedia.kind == kind, CelebrationMedia.is_active == True  # noqa: E712
        )
    ):
        old.is_active = False

    media = CelebrationMedia(
        kind=kind,
        file_id=file_id,
        file_type=file_type if file_type in {"video", "animation"} else "video",
        caption=(caption or None),
        is_active=True,
        uploaded_by=actor_id,
    )
    db.add(media)
    await db.commit()
    await db.refresh(media)
    return media


async def disable_media(db: AsyncSession, kind: str) -> int:
    """Turni o'chiradi (video tarixda qoladi, lekin e'lon yuborilmaydi)."""
    rows = list(
        await db.scalars(
            select(CelebrationMedia).where(
                CelebrationMedia.kind == kind, CelebrationMedia.is_active == True  # noqa: E712
            )
        )
    )
    for m in rows:
        m.is_active = False
    if rows:
        await db.commit()
    return len(rows)


async def _main_group_chat_id(db: AsyncSession) -> int | None:
    """Umumiy guruh — `MonitoredGroup(purpose="main")`, dasturchi bot orqali
    `/guruh_biriktir main` bilan belgilanadi (issiq lid bilan bir xil manzil)."""
    return await db.scalar(
        select(MonitoredGroup.chat_id).where(
            MonitoredGroup.purpose == "main", MonitoredGroup.is_active == True  # noqa: E712
        )
    )


def clap_keyboard(post_id: int, claps: int) -> dict:
    label = "👏 Tabriklash" if claps <= 0 else f"👏 Tabriklash ({claps})"
    return inline_keyboard([[(label, f"celebrate:clap:{post_id}")]])


async def _day_count(db: AsyncSession, kind: str, user_id: int | None, day: date) -> int:
    """Shu xodimning bugungi nechanchi tashrifi/shartnomasi ekani."""
    if user_id is None:
        return 0
    start, end = local_range_utc_naive(day, day)
    return (
        await db.scalar(
            select(func.count(CelebrationPost.id)).where(
                CelebrationPost.kind == kind,
                CelebrationPost.user_id == user_id,
                CelebrationPost.created_at >= start,
                CelebrationPost.created_at < end,
            )
        )
    ) or 0


def build_caption(
    kind: str, who: str | None, nth: int, stage_name: str | None, extra: str | None
) -> str:
    """Video ostidagi izoh. `nth` — shu xodimning bugungi nechanchisi."""
    lines = [_KIND_TITLES.get(kind, "🎉")]
    if who:
        lines.append(f"🙍 <b>{who}</b>")
    else:
        lines.append("🙍 Mas'ul: <i>CRM'da biriktirilmagan</i>")
    if nth > 1:
        lines.append(f"📈 Bugun {nth}-{_KIND_LABELS.get(kind, '').lower()}i")
    if stage_name:
        lines.append(f"🏷 Bosqich: {stage_name}")
    if extra:
        lines.append("")
        lines.append(extra)
    return "\n".join(lines)


async def _pending_events(db: AsyncSession, limit: int) -> list[tuple[LeadEvent, str]]:
    """E'lon qilinmagan, muddati o'tmagan mos voqealar (eng eskisidan)."""
    kinds = {
        k: _kind_status_ids(k)
        for k in (CelebrationKind.visit.value, CelebrationKind.contract.value)
    }
    all_ids = {i for ids in kinds.values() for i in ids}
    if not all_ids:
        return []

    since = datetime.utcnow() - timedelta(minutes=_LOOKBACK_MINUTES)
    announced = select(CelebrationPost.lead_event_id)
    rows = await db.scalars(
        select(LeadEvent)
        .where(
            LeadEvent.detected_at >= since,
            LeadEvent.event_type != "first_seen",
            LeadEvent.to_pipe_status_id.in_(all_ids),
            LeadEvent.id.notin_(announced),
        )
        .order_by(LeadEvent.detected_at)
        .limit(limit * 4)  # nomuvofiqlari filtrda tushib qoladi — zaxira bilan olamiz
    )

    out: list[tuple[LeadEvent, str]] = []
    for ev in rows:
        kind = event_kind(ev)
        if kind is None:
            continue
        out.append((ev, kind))
        if len(out) >= limit:
            break
    return out


async def announce_pending(db: AsyncSession, dry_run: bool = False) -> dict:
    """Kutayotgan tabriklarni guruhga yuboradi. Har daqiqada (cron) va
    webhook qayta ishlangandan keyin chaqiriladi."""
    pending = await _pending_events(db, _MAX_PER_TICK)
    if not pending:
        return {"ok": True, "sent": 0, "skipped": "voqea yo'q"}

    chat_id = await _main_group_chat_id(db)
    if not chat_id:
        return {"ok": True, "sent": 0, "skipped": "umumiy guruh biriktirilmagan"}

    users = {
        u.crm_visit_external_id: u
        for u in await db.scalars(select(User).where(User.crm_visit_external_id.isnot(None)))
    }

    sent, skipped_no_media = 0, 0
    for ev, kind in pending:
        media = await active_media(db, kind)
        if media is None:
            skipped_no_media += 1
            continue

        user = users.get(str(ev.to_responsible_id)) if ev.to_responsible_id else None
        who = user.full_name.strip() if user else (ev.to_responsible_name or None)
        nth = await _day_count(db, kind, user.id if user else None, date.today()) + 1
        caption = build_caption(kind, who, nth, ev.to_stage_name, media.caption)

        if dry_run:
            sent += 1
            continue

        post = CelebrationPost(
            kind=kind,
            lead_event_id=ev.id,
            crm_lead_id=ev.crm_lead_id,
            user_id=user.id if user else None,
            chat_id=chat_id,
        )
        db.add(post)
        try:
            # AVVAL yozamiz, keyin yuboramiz: UNIQUE cheklovi shu yerda
            # ishlaydi va parallel ikkinchi jarayon shu voqeani yubormaydi.
            await db.commit()
        except IntegrityError:
            await db.rollback()
            continue
        await db.refresh(post)

        resp = await send_file_id(
            chat_id,
            media.file_id,
            media.file_type,
            caption=caption,
            reply_markup=clap_keyboard(post.id, 0),
        )
        if resp is None:
            # Telegram qabul qilmadi (masalan file_id eskirgan) — matn bilan
            # bo'lsa ham xabar bersin, tabrik butunlay yo'qolmasin.
            resp = await send_message(chat_id, caption, reply_markup=clap_keyboard(post.id, 0))
            logger.warning("Tabrik videosi yuborilmadi, matn bilan almashtirildi (kind=%s)", kind)
        msg_id = ((resp or {}).get("result") or {}).get("message_id")
        if msg_id:
            post.message_id = msg_id
            await db.commit()
        sent += 1

    return {
        "ok": True,
        "sent": sent,
        "pending": len(pending),
        "skipped_no_media": skipped_no_media,
        "dry_run": dry_run,
    }


async def register_clap(db: AsyncSession, post_id: int, telegram_id: int) -> dict:
    """«👏 Tabriklash» bosilishi. Takroriy bosish sanoqni oshirmaydi."""
    post = await db.get(CelebrationPost, post_id)
    if post is None:
        return {"ok": False, "reason": "post topilmadi"}

    existing = await db.scalar(
        select(CelebrationClap).where(
            CelebrationClap.post_id == post_id, CelebrationClap.telegram_id == telegram_id
        )
    )
    if existing is not None:
        return {"ok": True, "already": True, "claps": post.claps}

    db.add(CelebrationClap(post_id=post_id, telegram_id=telegram_id))
    post.claps = (post.claps or 0) + 1
    try:
        await db.commit()
    except IntegrityError:
        # Ikki bosish bir vaqtda kelgan — ikkinchisi hisobga olinmaydi
        await db.rollback()
        await db.refresh(post)
        return {"ok": True, "already": True, "claps": post.claps}

    if post.chat_id and post.message_id:
        await edit_reply_markup(
            post.chat_id, post.message_id, clap_keyboard(post.id, post.claps)
        )
    return {"ok": True, "already": False, "claps": post.claps}


async def send_test(db: AsyncSession, kind: str, actor: User) -> dict:
    """Rahbar «Sinov yuborish» bosganda — o'ZIGA (guruhga emas) yuboradi.

    Ataylab shaxsiy chatga: guruhga sinov videosi tashlash xodimlarni
    chalg'itadi va "shartnoma bo'ldi" degan yolg'on signal beradi."""
    media = await active_media(db, kind)
    if media is None:
        return {"ok": False, "reason": "Bu tur uchun video yuklanmagan"}
    if not actor.telegram_id:
        return {"ok": False, "reason": "Telegram hisobingiz bog'lanmagan"}

    caption = build_caption(
        kind, actor.full_name.strip(), 1, _KIND_LABELS.get(kind), media.caption
    )
    resp = await send_file_id(
        actor.telegram_id,
        media.file_id,
        media.file_type,
        caption=f"🧪 <i>SINOV — guruhga yuborilmadi</i>\n\n{caption}",
    )
    return {"ok": resp is not None, "kind": kind}
