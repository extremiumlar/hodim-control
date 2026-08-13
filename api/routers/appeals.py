"""E'tiroz va shikoyatlar (KUNDALIK_ETIROZ_REJASI.md, Bosqich 4).

Xodim ikki xil murojaat yubora oladi:
  - **e'tiroz** (`objection`) — ANIQ qarorga qarshi: davomat kuni yoki oylik
    varaqasi. Har doim manzilli (`ref_date` / `ref_period`).
  - **shikoyat** (`complaint`) — erkin mavzu (ish sharoiti, jamoa, boshqa).
    Qabul qiluvchini xodim O'ZI tanlaydi (HR yoki Boshliq) va xohlasa anonim
    yuboradi.

⚠️ ENG MUHIM TAMOYIL: bu modul HECH NARSANI HISOBLAMAYDI. E'tiroz qondirilsa
davomat/pul tuzatish FAQAT mavjud mexanizmlar orqali bajariladi (`ExcusedDay`
+ `recompute_attendance`, `PayrollAdjustment`, qulf bo'lsa admin unlock).
Qaror chiqqanda API faqat "endi tuzatishni kiriting" deb YO'L KO'RSATADI —
avtomatik hech narsa o'zgartirmaydi. Aks holda payslip raqami ikki xil yo'ldan
kelib, qaysi biri to'g'riligini hech kim ayta olmasdi
(`ExplanationRequest`da isbotlangan tamoyil, db/models.py:938-942).

MAXFIYLIK: HR faqat O'ZIGA yuborilgan murojaatlarni ko'radi — shikoyat HR
haqida bo'lishi mumkin. Boshliq va Dasturchi hammasini ko'radi.
"""
import html
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user, get_db, require_roles, verify_bot_secret
from api.notify import notify_user
from api.schemas import (
    AppealActorBot,
    AppealAttendanceTarget,
    AppealBotCreate,
    AppealCreateBase,
    AppealDecide,
    AppealDecideBot,
    AppealMeCreate,
    AppealOut,
    AppealSlaTick,
)
from api.services.push import Category
from api.telegram_notify import inline_keyboard
from api.timeutil import today_local
from db.models import (
    APPEAL_OPEN_STATUSES,
    Appeal,
    AppealKind,
    AppealStatus,
    AppealTopic,
    Attendance,
    AttendanceStatus,
    AuditLog,
    Role,
    User,
)

router = APIRouter(prefix="/appeals", tags=["appeals"])

# Murojaatni ko'radigan/hal qiladigan rollar. ROP ATAYLAB YO'Q: murojaatlarda
# oylik summasi va shaxsiy shikoyat bo'ladi (excused_days'dagi maxfiylik
# qoidasi bilan bir ruh), qaror esa HR/Boshliq vakolatida.
MANAGE_ROLES = (Role.hr.value, Role.boss.value, Role.dasturchi.value)

# Bir xodimda bir vaqtda ochiq turadigan murojaatlar chegarasi — spamga qarshi.
MAX_OPEN_PER_USER = 5

# SLA (8-bo'lim, savol 2 QAROR): 3 kun — qabul qiluvchiga eslatma;
# 5 kun — Boshliqqa eskalatsiya. Ikkalasi ham BIR MARTA (iz ustunlari).
SLA_REMIND_DAYS = 3
SLA_ESCALATE_DAYS = 5

# E'tiroz uchun nishon oynasi: bot oxirgi shuncha kundagi kechikish/kelmaslik
# kunlarini tugma qilib beradi.
TARGET_LOOKBACK_DAYS = 30

_KIND_LABELS = {
    AppealKind.objection.value: "E'tiroz",
    AppealKind.complaint.value: "Shikoyat",
}
_TOPIC_LABELS = {
    AppealTopic.attendance.value: "Davomat",
    AppealTopic.payroll.value: "Oylik",
    AppealTopic.work_env.value: "Ish sharoiti",
    AppealTopic.team.value: "Jamoa",
    AppealTopic.other.value: "Boshqa",
}

# `accepted` bo'lganda qabul qiluvchiga ko'rsatiladigan KEYINGI QADAM. API
# hech narsani o'zgartirmaydi — tuzatish mavjud mexanizmlar orqali qo'lda
# kiritiladi (moduldagi asosiy tamoyil).
_NEXT_STEP = {
    AppealTopic.attendance.value: (
        "Endi tuzatishni kiriting: «Sababli kunlar» bo'limidan xodim uchun "
        "o'sha kunni belgilang (davomat va jarima o'z-o'zidan qayta hisoblanadi)."
    ),
    AppealTopic.payroll.value: (
        "Endi tuzatishni kiriting: «Ish haqi» bo'limida o'sha davr uchun "
        "tuzatish (adjustment) qo'shing. Davr qulflangan bo'lsa Dasturchi ochadi."
    ),
}


def _to_out(item: Appeal, full_name: str | None) -> AppealOut:
    """Anonim shikoyatda shaxs BACKENDDA yashiriladi — frontendda emas.
    Aks holda ism javobda ketaverib, brauzer konsolida ko'rinib qolardi."""
    anon = item.is_anonymous
    return AppealOut(
        id=item.id,
        user_id=None if anon else item.user_id,
        user_full_name=None if anon else full_name,
        kind=item.kind,
        topic=item.topic,
        text=item.text,
        is_anonymous=anon,
        recipient_role=item.recipient_role,
        ref_date=item.ref_date,
        ref_period=item.ref_period,
        file_id=item.file_id,
        file_type=item.file_type,
        status=item.status,
        review_started_at=item.review_started_at,
        decided_by=item.decided_by,
        decided_at=item.decided_at,
        decision_note=item.decision_note,
        created_at=item.created_at,
    )


def _to_out_self(item: Appeal, full_name: str) -> AppealOut:
    """Xodimning O'Z ko'rinishi — anonim bo'lsa ham o'zini ko'radi.

    Anonimlik RAHBARDAN yashirish uchun; muallif o'z murojaatini ismi bilan
    ko'rishi kerak, aks holda "mening murojaatlarim" ro'yxati egasiz
    yozuvlardan iborat bo'lib qolardi."""
    out = _to_out(item, full_name)
    out.user_id = item.user_id
    out.user_full_name = full_name
    return out


async def _to_out_many(items: list[Appeal], db: AsyncSession) -> list[AppealOut]:
    """N+1 dan qochib ismlarni bitta so'rovda oladi (excused_days naqshi)."""
    ids = {i.user_id for i in items if not i.is_anonymous}
    names = {
        u.id: u.full_name
        for u in await db.scalars(select(User).where(User.id.in_(ids or {0})))
    }
    return [_to_out(i, names.get(i.user_id)) for i in items]


def _can_access(actor: User, item: Appeal) -> bool:
    """Boshliq/Dasturchi — hammasini; HR — faqat O'ZIGA yuborilganini.

    NEGA: shikoyat HR ning o'zi haqida bo'lishi mumkin. Agar HR Boshliqqa
    yuborilgan shikoyatni ko'ra olsa, «Kimga» tanlovining ma'nosi qolmaydi
    va xodim tizimga ishonmay qo'yadi."""
    if actor.role in (Role.boss.value, Role.dasturchi.value):
        return True
    return item.recipient_role == actor.role


async def _recipients(db: AsyncSession, item: Appeal) -> list[User]:
    """Murojaat kimga boradi. HR yo'q bo'lsa — Boshliqqa (excused_days:104-108
    dagi bir xil zaxira yo'li: murojaat hech kimga bormay qolmasin)."""
    users = list(
        await db.scalars(
            select(User).where(
                User.role == item.recipient_role,
                User.is_active.is_(True),
                User.telegram_id.isnot(None),
            )
        )
    )
    if not users and item.recipient_role != Role.boss.value:
        users = list(
            await db.scalars(
                select(User).where(
                    User.role == Role.boss.value,
                    User.is_active.is_(True),
                    User.telegram_id.isnot(None),
                )
            )
        )
    return users


def _header(item: Appeal, author: str) -> str:
    """Xabar sarlavhasi — kim, nima haqida, qaysi manzil bo'yicha."""
    ref = ""
    if item.ref_date:
        ref = f"\nSana: {item.ref_date}"
    elif item.ref_period:
        ref = f"\nDavr: {item.ref_period}"
    icon = "⚖️" if item.kind == AppealKind.objection.value else "📨"
    return (
        f"{icon} <b>{_KIND_LABELS[item.kind]}</b> — {_TOPIC_LABELS.get(item.topic, item.topic)}\n"
        f"Kimdan: {author}{ref}\n\n{html.escape(item.text)}"
    )


async def _create_appeal(db: AsyncSession, user: User, payload: AppealCreateBase) -> AppealOut:
    """Bot va web adapterlari SHU yordamchiga boradi (excused_days naqshi) —
    spam chegarasi, manzil qoidasi va xabar yuborish bir joyda qoladi."""
    open_count = len(
        list(
            await db.scalars(
                select(Appeal).where(
                    Appeal.user_id == user.id, Appeal.status.in_(APPEAL_OPEN_STATUSES)
                )
            )
        )
    )
    if open_count >= MAX_OPEN_PER_USER:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Sizda {open_count} ta hal qilinmagan murojaat bor. "
            "Avval ular ko'rib chiqilsin, keyin yangisini yuborasiz.",
        )

    # E'tiroz HAR DOIM HR'ga: u aniq qarorga qarshi va tekshirish HR ishi.
    # «Kimga» tanlovi faqat shikoyatda ma'noga ega (shikoyat HR haqida
    # bo'lishi mumkin) — sxema buni tekshirmaydi, chunki bu ruxsat emas,
    # marshrutlash qoidasi.
    recipient = (
        Role.hr.value
        if payload.kind == AppealKind.objection.value
        else payload.recipient_role
    )

    item = Appeal(
        user_id=user.id,
        kind=payload.kind,
        topic=payload.topic,
        text=payload.text.strip(),
        is_anonymous=payload.is_anonymous,
        recipient_role=recipient,
        ref_date=payload.ref_date,
        ref_period=payload.ref_period,
        file_id=payload.file_id,
        file_type=payload.file_type,
    )
    db.add(item)
    await db.flush()

    db.add(
        AuditLog(
            actor_id=user.id,
            action="appeal_created",
            target_user_id=user.id,
            before=None,
            after={
                "id": item.id,
                "kind": item.kind,
                "topic": item.topic,
                "recipient_role": item.recipient_role,
                "is_anonymous": item.is_anonymous,
                "ref_date": item.ref_date.isoformat() if item.ref_date else None,
                "ref_period": item.ref_period,
            },
        )
    )
    await db.commit()
    await db.refresh(item)

    author = "Anonim xodim" if item.is_anonymous else user.full_name
    keyboard = inline_keyboard(
        [
            [
                ("🔎 O'rganyapman", f"appeal_review:{item.id}"),
                ("✅ Hal qilish", f"appeal_decide:{item.id}"),
            ]
        ]
    )
    for rec in await _recipients(db, item):
        # force_telegram: qaror tugmalari FAQAT botda — push'da tugma yo'q,
        # ya'ni xabar push kanalida qolib ketsa amal bajarilmay qolardi
        # (api/notify.py:66-72).
        await notify_user(
            db, rec, Category.APPEALS, _header(item, author),
            reply_markup=keyboard, force_telegram=True, data={"path": "/appeals"},
        )

    # Javob MUALLIFNING o'ziga qaytadi — anonim bo'lsa ham o'zini ko'radi
    # (`/appeals/me` ro'yxati bilan bir xil ko'rinish; aks holda yaratilgan
    # yozuv "kimniki noma'lum" bo'lib qaytardi va mijoz uni o'z ro'yxatidagi
    # yozuv bilan bog'lay olmasdi).
    return _to_out_self(item, user.full_name)


async def _get_for_actor(db: AsyncSession, item_id: int, actor: User) -> Appeal:
    item = await db.get(Appeal, item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Murojaat topilmadi")
    if not _can_access(actor, item):
        # 404, 403 emas: Boshliqqa yuborilgan shikoyat MAVJUDLIGI ham
        # oshkor bo'lmasin (maxfiylik qoidasining davomi).
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Murojaat topilmadi")
    return item


# ─── Xodim: bot adapterlari (X-Bot-Secret, shaxs = telegram_id) ─────────────────


@router.post("/bot", response_model=AppealOut, dependencies=[Depends(verify_bot_secret)])
async def create_appeal_bot(payload: AppealBotCreate, db: AsyncSession = Depends(get_db)) -> AppealOut:
    user = await db.scalar(select(User).where(User.telegram_id == payload.telegram_id))
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Foydalanuvchi topilmadi")
    return await _create_appeal(db, user, payload)


@router.get(
    "/bot/my/{telegram_id}",
    response_model=list[AppealOut],
    dependencies=[Depends(verify_bot_secret)],
)
async def my_appeals_bot(telegram_id: int, db: AsyncSession = Depends(get_db)) -> list[AppealOut]:
    user = await db.scalar(select(User).where(User.telegram_id == telegram_id))
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Foydalanuvchi topilmadi")
    items = list(
        await db.scalars(
            select(Appeal)
            .where(Appeal.user_id == user.id)
            .order_by(Appeal.created_at.desc())
            .limit(10)
        )
    )
    # O'z ro'yxatida anonimlik yashirilmaydi — xodim o'z murojaatini ko'radi.
    return [_to_out_self(i, user.full_name) for i in items]


@router.get(
    "/bot/attendance-targets/{telegram_id}",
    response_model=list[AppealAttendanceTarget],
    dependencies=[Depends(verify_bot_secret)],
)
async def attendance_targets_bot(
    telegram_id: int, db: AsyncSession = Depends(get_db)
) -> list[AppealAttendanceTarget]:
    """Davomat e'tirozi uchun nishonlar — oxirgi 30 kundagi kechikish/kelmaslik.

    Bot shularni tugma qilib beradi: xodim sanani qo'lda termaydi va e'tiroz
    HAR DOIM haqiqiy davomat yozuviga bog'lanadi."""
    user = await db.scalar(select(User).where(User.telegram_id == telegram_id))
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Foydalanuvchi topilmadi")
    since = today_local() - timedelta(days=TARGET_LOOKBACK_DAYS)
    rows = list(
        await db.scalars(
            select(Attendance)
            .where(
                Attendance.user_id == user.id,
                Attendance.date >= since,
                Attendance.status.in_(
                    (AttendanceStatus.late.value, AttendanceStatus.absent.value)
                ),
            )
            .order_by(Attendance.date.desc())
        )
    )
    return [
        AppealAttendanceTarget(date=r.date, status=r.status, late_minutes=r.late_minutes)
        for r in rows
    ]


# ─── Xodim: web/mobil (JWT, shaxs = token) ─────────────────────────────────────


@router.post("/me", response_model=AppealOut)
async def create_my_appeal(
    payload: AppealMeCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AppealOut:
    """Sxema ATAYLAB boshqa (`AppealMeCreate`): `telegram_id` YO'Q, shaxs
    tokendan — mijoz boshqa birov nomidan murojaat yubora olmaydi."""
    return await _create_appeal(db, user, payload)


@router.get("/me", response_model=list[AppealOut])
async def list_my_appeals(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[AppealOut]:
    items = list(
        await db.scalars(
            select(Appeal)
            .where(Appeal.user_id == user.id)
            .order_by(Appeal.created_at.desc())
            .limit(50)
        )
    )
    return [_to_out_self(i, user.full_name) for i in items]


# ─── Qabul qiluvchi (HR / Boshliq / Dasturchi) ─────────────────────────────────


@router.get("", response_model=list[AppealOut])
async def list_appeals(
    status_filter: str | None = None,
    kind: str | None = None,
    actor: User = Depends(require_roles(*MANAGE_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> list[AppealOut]:
    query = select(Appeal).order_by(Appeal.created_at.desc())
    if status_filter:
        query = query.where(Appeal.status == status_filter)
    if kind:
        query = query.where(Appeal.kind == kind)
    # Maxfiylik: HR faqat o'ziga yuborilganini (`_can_access` bilan bir qoida,
    # lekin SQL darajasida — ro'yxat so'rovi hammasini o'qib keyin
    # filtrlamasin).
    if actor.role == Role.hr.value:
        query = query.where(Appeal.recipient_role == Role.hr.value)
    items = list(await db.scalars(query))
    return await _to_out_many(items, db)


async def _start_review(db: AsyncSession, item: Appeal, actor: User) -> AppealOut:
    """«O'rganyapman» — oraliq holat. Kichik narsa, lekin xodim uchun muhim:
    murojaat ko'rilgani bilinadi va u javobsizlikdan xavotirlanmaydi."""
    if item.status != AppealStatus.pending.value:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Bu murojaat allaqachon ko'rib chiqilmoqda yoki hal qilingan"
        )
    item.status = AppealStatus.in_review.value
    item.review_started_by = actor.id
    item.review_started_at = datetime.utcnow()

    db.add(
        AuditLog(
            actor_id=actor.id,
            action="appeal_review_started",
            target_user_id=item.user_id,
            before={"status": AppealStatus.pending.value},
            after={"id": item.id, "status": item.status},
        )
    )
    await db.commit()
    await db.refresh(item)

    author = await db.get(User, item.user_id)
    if author is not None:
        await notify_user(
            db, author, Category.DECISIONS,
            f"🔎 Murojaatingiz ko'rib chiqilmoqda ({_KIND_LABELS[item.kind]}).\n"
            "Javob tayyor bo'lganda shu yerda xabar beramiz.",
            data={"path": "/me/appeals"},
        )
    return _to_out(item, None if item.is_anonymous else (author.full_name if author else None))


async def _decide(db: AsyncSession, item: Appeal, actor: User, decision: str, note: str) -> dict:
    """Yakuniy qaror. Qaytadi: `{"appeal": ..., "next_step": ...}` —
    `next_step` qabul qiluvchiga ko'rsatiladigan KEYINGI QADAM matni
    (avtomatik tuzatish YO'Q, moduldagi asosiy tamoyil)."""
    if item.status not in APPEAL_OPEN_STATUSES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Bu murojaat allaqachon hal qilingan")

    # Qaror turi murojaat turiga mos bo'lishi shart: e'tiroz "qondirildi/rad",
    # shikoyat "hal qilindi/rad" bo'ladi. Aralashsa hisobot ma'nosini
    # yo'qotadi (nechta e'tiroz qondirilgani sanab bo'lmaydi).
    allowed = (
        {AppealStatus.accepted.value, AppealStatus.rejected.value}
        if item.kind == AppealKind.objection.value
        else {AppealStatus.resolved.value, AppealStatus.rejected.value}
    )
    if decision not in allowed:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"{_KIND_LABELS[item.kind]} uchun bu qaror mos emas: {decision}",
        )

    before_status = item.status
    item.status = decision
    item.decided_by = actor.id
    item.decided_at = datetime.utcnow()
    item.decision_note = note.strip()

    db.add(
        AuditLog(
            actor_id=actor.id,
            action="appeal_decided",
            target_user_id=item.user_id,
            before={"status": before_status},
            after={
                "id": item.id,
                "kind": item.kind,
                "topic": item.topic,
                "status": item.status,
                "note": item.decision_note,
            },
        )
    )
    await db.commit()
    await db.refresh(item)

    author = await db.get(User, item.user_id)
    if author is not None:
        verdict = {
            AppealStatus.accepted.value: "✅ E'tirozingiz QONDIRILDI",
            AppealStatus.resolved.value: "✅ Murojaatingiz hal qilindi",
            AppealStatus.rejected.value: "❌ Murojaatingiz rad etildi",
        }[item.status]
        tail = (
            "\n\nTuzatish tez orada kiritiladi — natijani o'z bo'limingizda ko'rasiz."
            if item.status == AppealStatus.accepted.value
            else ""
        )
        await notify_user(
            db, author, Category.DECISIONS,
            f"{verdict}\nIzoh: {html.escape(item.decision_note or '')}{tail}",
            data={"path": "/me/appeals"},
        )

    next_step = (
        _NEXT_STEP.get(item.topic) if item.status == AppealStatus.accepted.value else None
    )
    out = _to_out(item, None if item.is_anonymous else (author.full_name if author else None))
    return {"appeal": out.model_dump(mode="json"), "next_step": next_step}


@router.post("/{item_id}/review", response_model=AppealOut)
async def review_appeal(
    item_id: int,
    actor: User = Depends(require_roles(*MANAGE_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> AppealOut:
    item = await _get_for_actor(db, item_id, actor)
    return await _start_review(db, item, actor)


@router.post("/{item_id}/review/bot", response_model=AppealOut, dependencies=[Depends(verify_bot_secret)])
async def review_appeal_bot(
    item_id: int, payload: AppealActorBot, db: AsyncSession = Depends(get_db)
) -> AppealOut:
    actor = await db.scalar(select(User).where(User.telegram_id == payload.telegram_id))
    if not actor or not actor.is_active or actor.role not in MANAGE_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Bu amal uchun ruxsat yo'q")
    item = await _get_for_actor(db, item_id, actor)
    return await _start_review(db, item, actor)


@router.post("/{item_id}/decide")
async def decide_appeal(
    item_id: int,
    payload: AppealDecide,
    actor: User = Depends(require_roles(*MANAGE_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    item = await _get_for_actor(db, item_id, actor)
    return await _decide(db, item, actor, payload.decision, payload.note)


@router.post("/{item_id}/decide/bot", dependencies=[Depends(verify_bot_secret)])
async def decide_appeal_bot(
    item_id: int, payload: AppealDecideBot, db: AsyncSession = Depends(get_db)
) -> dict:
    actor = await db.scalar(select(User).where(User.telegram_id == payload.telegram_id))
    if not actor or not actor.is_active or actor.role not in MANAGE_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Bu amal uchun ruxsat yo'q")
    item = await _get_for_actor(db, item_id, actor)
    return await _decide(db, item, actor, payload.decision, payload.note)


# ─── SLA (scheduler) ───────────────────────────────────────────────────────────


@router.post("/sla-tick", dependencies=[Depends(verify_bot_secret)])
async def appeals_sla_tick(payload: AppealSlaTick, db: AsyncSession = Depends(get_db)) -> dict:
    """Javobsiz qolgan murojaatlar: 3 kundan keyin qabul qiluvchiga eslatma,
    5 kundan keyin Boshliqqa eskalatsiya.

    Mantiq `api/services/cron_jobs.py` da — cPanel cron uni SAYTGA so'rov
    yubormasdan, o'z jarayonida bajaradi. Bu endpoint Docker/scheduler rejimi
    va qo'lda `dry_run` tekshiruvi uchun saqlanadi."""
    from api.services.cron_jobs import appeals_sla_tick as _tick

    return await _tick(db, dry_run=payload.dry_run)
