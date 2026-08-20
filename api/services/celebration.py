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

from api.telegram_notify import (
    edit_reply_markup,
    extract_file_id,
    inline_keyboard,
    send_file_id,
    send_media_file,
    send_message,
)
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



# Telegram Bot API bir so'rovda 50 MB gacha fayl qabul qiladi — 45 MB da
# to'xtatamiz, chunki multipart o'rami va sarlavhalar ham joy egallaydi.
MAX_UPLOAD_BYTES = 45 * 1024 * 1024


def guess_file_type(filename: str, content_type: str | None) -> str | None:
    """Yuklangan fayl video mi, GIF mi — yoki umuman yaramaydimi.

    GIF ALOHIDA: Telegram uni `sendAnimation` bilan yuboradi, `sendVideo`
    bilan yuborilsa oddiy faylga aylanib qoladi (ovozsiz avto-o'ynash yo'q)."""
    name = (filename or "").lower()
    ctype = (content_type or "").lower()
    if name.endswith(".gif") or ctype == "image/gif":
        return "animation"
    if ctype.startswith("video/") or name.endswith((".mp4", ".mov", ".m4v", ".webm")):
        return "video"
    return None


async def upload_and_set(
    db: AsyncSession,
    kind: str,
    content: bytes,
    filename: str,
    content_type: str | None,
    caption: str | None,
    actor: User,
) -> dict:
    """Sayt panelidan kelgan faylni Telegram'ga yuklab, `file_id` sini saqlaydi.

    Fayl AKTYORNING SHAXSIY chatiga yuboriladi (guruhga emas) — bu ham
    yuklashning tabiiy tasdig'i bo'ladi: rahbar videoni darhol ko'radi va
    guruhga qanday chiqishini tasavvur qiladi."""
    file_type = guess_file_type(filename, content_type)
    if file_type is None:
        return {"ok": False, "reason": "Faqat video (mp4/mov/webm) yoki GIF yuklash mumkin"}
    if not content:
        return {"ok": False, "reason": "Fayl bo'sh"}
    if len(content) > MAX_UPLOAD_BYTES:
        mb = len(content) / 1024 / 1024
        return {"ok": False, "reason": f"Fayl juda katta ({mb:.0f} MB). Chegara — 45 MB"}
    if not actor.telegram_id:
        return {
            "ok": False,
            "reason": "Telegram hisobingiz bog'lanmagan — video Telegram orqali yuboriladi, "
            "avval botga /start bosing",
        }

    resp = await send_media_file(
        actor.telegram_id,
        content,
        filename or "tabrik.mp4",
        file_type,
        caption=f"🎬 <i>Tabrik videosi yuklandi — {_KIND_LABELS.get(kind, kind)}</i>",
    )
    file_id = extract_file_id(resp)
    if not file_id:
        return {
            "ok": False,
            "reason": "Telegram faylni qabul qilmadi. Botni bloklamaganingizni va fayl "
            "hajmini tekshirib qayta urinib ko'ring",
        }

    media = await set_media(db, kind, file_id, file_type, caption, actor.id)
    return {"ok": True, "kind": kind, "file_type": media.file_type}


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


# ─────────────────────────────────────────────────────────────
# ODAM HODISALARI — tug'ilgan kun va ish yubileyi (TZ 3.14 / S-22)
#
# ⚠️ YANGI MEXANIZM QURILMAYDI (TZ talabi). Xuddi shu jadval, xuddi shu
# video va xuddi shu «👏 Tabriklash» tugmasi. Farqi: manba CRM voqeasi
# emas, kundalik cron — shuning uchun takrorlanishdan `dedupe_key`
# qo'riqlaydi (`lead_event_id` odam hodisasida bo'sh).
# ─────────────────────────────────────────────────────────────

_PEOPLE_TITLES = {
    CelebrationKind.birthday.value: "🎂 <b>TUG'ILGAN KUN!</b>",
    CelebrationKind.anniversary.value: "🏆 <b>ISH YUBILEYI!</b>",
}


def _people_dedupe_key(kind: str, user_id: int, year: int) -> str:
    """`birthday:7:2026` — yiliga bir marta."""
    return f"{kind}:{user_id}:{year}"


def _anniversary_years(hire: date, today: date) -> int | None:
    """Bugun nechanchi yubiley. Yubiley bo'lmasa `None`.

    29-fevralda ishga kirganlar: oddiy yillarda 28-fevral hisoblanadi —
    aks holda ularning yubileyi to'rt yilda bir marta nishonlanardi."""
    if hire.month == 2 and hire.day == 29:
        nishon = (2, 28) if today.year % 4 or (today.year % 100 == 0 and today.year % 400) else (2, 29)
    else:
        nishon = (hire.month, hire.day)
    if (today.month, today.day) != nishon:
        return None
    yillar = today.year - hire.year
    return yillar if yillar >= 1 else None


async def people_events(db: AsyncSession, today: date) -> list[tuple[User, str, int]]:
    """Bugungi tug'ilgan kun va yubileylar: `(xodim, kind, yosh_yoki_yil)`.

    ⚠️ Sanasi kiritilmagan xodim uchun tizim JIM turadi (TZ qabul
    mezoni) — bilmagan narsani tabriklab bo'lmaydi."""
    rows = list(await db.scalars(select(User).where(User.is_active.is_(True))))
    out: list[tuple[User, str, int]] = []
    for u in rows:
        bd = getattr(u, "birth_date", None)
        if bd and (bd.month, bd.day) == (today.month, today.day):
            out.append((u, CelebrationKind.birthday.value, today.year - bd.year))
        if u.hire_date:
            yillar = _anniversary_years(u.hire_date, today)
            if yillar:
                out.append((u, CelebrationKind.anniversary.value, yillar))
    return out


def build_people_caption(kind: str, who: str, n: int, extra: str | None) -> str:
    lines = [_PEOPLE_TITLES.get(kind, "🎉"), f"🙍 <b>{who}</b>"]
    if kind == CelebrationKind.birthday.value:
        #  Yosh faqat mantiqiy bo'lsa yoziladi: noto'g'ri kiritilgan
        #  sana tufayli «120 yosh» chiqib, tabrik masxaraga aylanmasin.
        if 14 <= n <= 90:
            lines.append(f"🎈 {n} yosh")
    else:
        lines.append(f"🏢 Kompaniyada {n} yil")
    if extra:
        lines += ["", extra]
    return "\n".join(lines)


async def announce_people(db: AsyncSession, dry_run: bool = False) -> dict:
    """Bugungi tug'ilgan kun va yubileylarni guruhga chiqaradi.

    ⚠️ BIR MARTA (TZ qabul mezoni). `dedupe_key` UNIQUE: cron kuniga
    necha marta ishlasa ham ikkinchi post yaratilmaydi. Qator AVVAL
    yoziladi, keyin yuboriladi — parallel jarayon ham to'siladi."""
    from api.timeutil import today_local

    bugun = today_local()
    hodisalar = await people_events(db, bugun)
    if not hodisalar:
        return {"ok": True, "sent": 0, "found": 0}

    chat_id = await _main_group_chat_id(db)
    if chat_id is None:
        #  Guruh biriktirilmagan — bu XATO emas, sozlanmagan holat.
        return {"ok": True, "sent": 0, "found": len(hodisalar), "no_group": True}

    #  ⚠️ QIYMATLARNI OLDINDAN OLAMIZ. Pastda `IntegrityError` bo'lsa
    #  `rollback()` chaqiriladi va u sessiyadagi BARCHA obyektni bekor
    #  qiladi (`expire_on_commit=False` ga BOG'LIQ EMAS). Keyingi
    #  aylanishda `user.full_name` ga murojaat qilish async kontekstda
    #  `MissingGreenlet` bilan yiqilardi — ya'ni cron ikkinchi marta
    #  ishlagan zahoti (takroriy qo'riqchi ishga tushganda) butun tick
    #  o'lardi. Bu loyihada avval ham uchragan tuzoq
    #  (`background_jobs.py` dagi `tg_id` izohiga qarang).
    tayyor = [(u.id, u.full_name.strip(), k, n) for u, k, n in hodisalar]

    sent = 0
    skipped_no_media = 0
    for user_id, full_name, kind, n in tayyor:
        media = await active_media(db, kind)
        if media is None:
            #  Video yuklanmagan bo'lsa MATN bilan yuboriladi: tug'ilgan
            #  kun HR ning sozlamasi tufayli o'tkazib yuborilmasin
            #  (tashrif/shartnomadan farqi shu — u yerda jim turiladi,
            #  chunki u kunda o'nlab marta takrorlanadi).
            skipped_no_media += 1
        caption = build_people_caption(kind, full_name, n,
                                       media.caption if media else None)
        if dry_run:
            sent += 1
            continue

        post = CelebrationPost(
            kind=kind,
            lead_event_id=None,
            crm_lead_id=None,
            dedupe_key=_people_dedupe_key(kind, user_id, bugun.year),
            user_id=user_id,
            chat_id=chat_id,
        )
        db.add(post)
        try:
            await db.commit()
        except IntegrityError:
            #  Bugun allaqachon yuborilgan.
            await db.rollback()
            continue
        await db.refresh(post)

        resp = None
        if media is not None:
            resp = await send_file_id(
                chat_id, media.file_id, media.file_type,
                caption=caption, reply_markup=clap_keyboard(post.id, 0),
            )
        if resp is None:
            resp = await send_message(chat_id, caption,
                                      reply_markup=clap_keyboard(post.id, 0))
        msg_id = ((resp or {}).get("result") or {}).get("message_id")
        if msg_id:
            post.message_id = msg_id
            await db.commit()
        sent += 1

    return {
        "ok": True,
        "sent": sent,
        "found": len(hodisalar),
        "skipped_no_media": skipped_no_media,
        "dry_run": dry_run,
    }


async def people_tomorrow(db: AsyncSession) -> list[tuple[User, str, int]]:
    """Ertangi tug'ilgan kun va yubileylar — HR ga eslatma uchun."""
    from datetime import timedelta as _td

    from api.timeutil import today_local

    return await people_events(db, today_local() + _td(days=1))
