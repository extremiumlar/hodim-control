"""Cron ticklarining SOF mantiqi — HTTP qatlamisiz.

NEGA (2026-08-13, SAYT_QOTISHI_TAHLIL.md Bosqich 4b): bu ishlar ilgari FAQAT
HTTP endpoint sifatida mavjud edi va cPanel'dagi cron ularni SAYTGA so'rov
yuborib bajarardi. Deploy'da konkurentlik = 1, ya'ni har bir cron chaqiruvi
yagona Passenger ishchisini band qilib, odamlarning so'rovlarini navbatga
tiqardi. Eng chastotalisi — `group_digest_tick`, u HAR DAQIQA ishlaydi.

Endi mantiq shu yerda, ikkita chaqiruvchi bilan:
  - `api/routers/*` — HTTP endpointlar SAQLANADI (Docker/scheduler rejimi
    `scheduler/main.py` ularni hamon chaqiradi);
  - `scripts/cron_tick.py` — cPanel rejimida shu funksiyalarni O'Z
    jarayonida chaqiradi.

Bu modul ATAYLAB FastAPI'dan mustaqil: cron uni import qilganda butun web
stack ko'tarilmasin (2026-07-31 dagi uzilish aynan shundan bo'lgan).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import settings
from api.timeutil import TASHKENT_TZ, today_local
from db.models import (
    AppLoginToken,
    Attendance,
    AttendanceReminder,
    GroupPostConfig,
    KnowledgeEntry,
    KnowledgeStatus,
    LoginAttempt,
    Role,
    TaskModel,
    TaskStatus,
    UsedTelegramLoginHash,
    User,
)

logger = logging.getLogger(__name__)


async def mark_overdue(db: AsyncSession) -> dict:
    """Muddati o'tgan `pending` vazifalarni `overdue` ga o'tkazadi.

    Muddatsiz (deadline=None) vazifalar tegilmaydi. Overdue vazifani xodim
    keyin ham «Bajardim» bilan yopa oladi."""
    result = await db.execute(
        update(TaskModel)
        .where(
            TaskModel.status == TaskStatus.pending.value,
            TaskModel.deadline.isnot(None),
            TaskModel.deadline < datetime.utcnow(),
        )
        .values(status=TaskStatus.overdue.value)
    )
    await db.commit()
    return {"marked_overdue": result.rowcount or 0}


async def cleanup_login_security(db: AsyncSession) -> dict:
    """Telegram login xavfsizligi: eskirgan replay-hash, rate-limit urinishi
    va ilova login tokenlarini o'chiradi — jadvallar cheksiz o'smasin.

    Chegara qiymatlari endpointdagi bilan AYNAN bir xil: hash 25 soat
    (24 soatlik `auth_date` oynasidan zahira bilan), urinish 1 soat (eng
    uzun oyna — dev-login 3600s), ilova tokeni 1 soat (o'zi 5 daqiqada
    eskiradi)."""
    now = datetime.utcnow()
    hash_cutoff = now - timedelta(hours=25)
    attempt_cutoff = now - timedelta(hours=1)
    app_token_cutoff = now - timedelta(hours=1)

    hash_result = await db.execute(
        delete(UsedTelegramLoginHash).where(UsedTelegramLoginHash.consumed_at < hash_cutoff)
    )
    attempt_result = await db.execute(
        delete(LoginAttempt).where(LoginAttempt.created_at < attempt_cutoff)
    )
    app_token_result = await db.execute(
        delete(AppLoginToken).where(AppLoginToken.created_at < app_token_cutoff)
    )
    await db.commit()
    return {
        "deleted_hashes": hash_result.rowcount,
        "deleted_attempts": attempt_result.rowcount,
        "deleted_app_login_tokens": app_token_result.rowcount,
    }


async def ad_spend_reminder_tick(db: AsyncSession) -> dict:
    """Reklama xarajati kiritilmagan bo'lsa eslatma (voronka 3-bosqich).

    NEGA KERAK: bu tizimning YAGONA qo'lda kiritiladigan qismi va reja
    aynan shuni asosiy xavf deb belgilagan — kiritilmasa CPL/CAC/ROMI
    hisoblanmaydi va zanjirning yuqori qismi ochilmay qoladi.

    Kimga: xarajatni kirita oladiganlar (Boshliq, Dasturchi, ROP) —
    shaxsiy DM, guruhga emas (pul raqamlari)."""
    from sqlalchemy import select

    from api.notify import notify_user
    from api.services import ad_spend
    from api.services.push import Category
    from db.models import Role, User

    missing = await ad_spend.missing_periods(db, months=2)
    if not missing:
        return {"ok": True, "missing": []}

    targets = list(
        await db.scalars(
            select(User).where(
                User.role.in_((Role.boss.value, Role.dasturchi.value, Role.rop.value)),
                User.is_active.is_(True),
                User.telegram_id.isnot(None),
            )
        )
    )
    davrlar = ", ".join(missing)
    text = (
        f"📣 <b>Reklama xarajati kiritilmagan</b>: {davrlar}\n\n"
        "Kiritilmasa bitta lid va bitta sotuv qancha pulga tushgani "
        "(CPL/CAC) hisoblanmaydi.\n"
        "Sayt → <b>Voronka</b> → «Reklama xarajati» — 5 daqiqalik ish."
    )
    for user in targets:
        await notify_user(db, user, Category.APPROVALS, text, data={"path": "/funnel"})
    return {"ok": True, "missing": missing, "notified": len(targets)}


async def holidays_reminder_tick(db: AsyncSession) -> dict:
    """Keyingi yil bayramlari kiritilmagan bo'lsa HR ga eslatma (TZ 2.9 / S-09).

    NEGA KERAK: bayram ro'yxati yiliga bir marta kiritiladi va aynan shuning
    uchun unutiladi. Unutilsa 1-yanvarda butun jamoa «kelmagan» bo'lib
    ushlanmaga tushadi — xato oyliq hisoblanguncha bilinmaydi.

    Dekabrda yuboriladi (cron sanani o'zi tanlaydi). Ro'yxat kiritilgan
    bo'lsa hech kimga xabar ketmaydi."""
    from sqlalchemy import select

    from api.notify import notify_user
    from api.services.holidays import missing_year
    from api.services.push import Category
    from db.models import Role, User

    from api.timeutil import today_local

    keyingi = today_local().year + 1
    if not await missing_year(db, keyingi):
        return {"ok": True, "year": keyingi, "missing": False}

    targets = list(
        await db.scalars(
            select(User).where(
                User.role.in_((Role.hr.value, Role.boss.value, Role.dasturchi.value)),
                User.is_active.is_(True),
                User.telegram_id.isnot(None),
            )
        )
    )
    text = (
        f"📅 <b>{keyingi}-yil bayramlari kiritilmagan</b>\n\n"
        "Kiritilmasa bayram kunlari oddiy ish kuni sifatida sanaladi: "
        "xodimlar «kelmagan» bo'lib ushlanmaga tushadi va normalar "
        "bajarilmagan ko'rinadi.\n"
        "Sayt → <b>Ish jadvali</b> → «Bayramlar»."
    )
    for user in targets:
        await notify_user(db, user, Category.APPROVALS, text,
                          data={"path": "/work-schedule"})
    return {"ok": True, "year": keyingi, "missing": True, "notified": len(targets)}


async def deadline_tick(db: AsyncSession) -> dict:
    """Yaqinlashayotgan muddatlar bo'yicha eslatma (yangi TZ 3.5 / S-13).

    KUNIGA BIR MARTA. Takrorlanmaslik `reminded_at` orqali: bugun
    eslatilgan band ikkinchi marta olinmaydi. Cron bir necha marta
    ishlasa ham (qayta ishga tushirish, ikki jarayon) xabar bitta ketadi.

    ⚠️ XABAR SHAXSIY, GURUHGA EMAS. Sinov muddati, tibbiy ko'rik — bular
    xodim haqidagi kadr ma'lumoti; guruhga chiqarish uni oshkor qilardi.

    ⚠️ BIR NECHA MUDDAT — BITTA XABAR. Kuniga o'nta band to'g'ri kelsa
    HR ga o'nta bildirishnoma ketardi va u ularni o'qimay qo'yardi.
    Har mas'ulga BITTA yig'ma xabar boradi."""
    from api.notify import notify_user
    from api.services import deadlines as svc
    from api.services.push import Category
    from api.timeutil import today_local
    from db.models import Role, User

    bugun = today_local()
    bandlar = [i for i in await svc.upcoming(db) if i.reminded_at != bugun]
    if not bandlar:
        return {"ok": True, "items": 0}

    # ── Mas'ul bo'yicha guruhlash ──
    # `responsible_role` bo'sh bo'lsa HR ga: muddatlar kadr ishi va
    # egasiz qolgan band hech kimga ko'rinmay yo'qolmasin.
    default_role = Role.hr.value
    rollar = {i.responsible_role or default_role for i in bandlar}

    oluvchilar = {
        r: list(
            await db.scalars(
                select(User).where(
                    User.role == r,
                    User.is_active.is_(True),
                    User.telegram_id.isnot(None),
                )
            )
        )
        for r in rollar
    }
    # Rol bo'yicha hech kim topilmasa (masalan HR ishdan bo'shagan) —
    # Boshliq/Dasturchi zaxira: xabar yo'qolmasin.
    zaxira = list(
        await db.scalars(
            select(User).where(
                User.role.in_((Role.boss.value, Role.dasturchi.value)),
                User.is_active.is_(True),
                User.telegram_id.isnot(None),
            )
        )
    )

    yuborildi = 0
    belgilanadi: list = []
    for rol, guruh in _group_by_role(bandlar, default_role).items():
        kimga = oluvchilar.get(rol) or zaxira
        if not kimga:
            continue
        matn = _deadline_text(guruh)
        for user in kimga:
            await notify_user(db, user, Category.APPROVALS, matn,
                              data={"path": "/deadlines"})
            yuborildi += 1
        belgilanadi.extend(guruh)

    await svc.mark_reminded(db, belgilanadi, bugun)
    return {"ok": True, "items": len(belgilanadi), "messages": yuborildi}


def _group_by_role(bandlar: list, default_role: str) -> dict:
    out: dict[str, list] = {}
    for i in bandlar:
        out.setdefault(i.responsible_role or default_role, []).append(i)
    return out


def _deadline_text(bandlar: list) -> str:
    """Bitta yig'ma xabar. O'tib ketganlar alohida ajratiladi — ular
    «yaqinlashayotgan» emas, allaqachon muammo."""
    otgan = [i for i in bandlar if i.days_left < 0]
    yaqin = [i for i in bandlar if i.days_left >= 0]

    qatorlar = ["⏳ <b>Muddatlar</b>", ""]
    if otgan:
        qatorlar.append("⛔ <b>Muddati o'tgan:</b>")
        for i in otgan:
            qatorlar.append(
                f"• {i.user_name} — {i.kind_label} "
                f"({i.due_date.isoformat()}, {abs(i.days_left)} kun oldin)"
            )
        qatorlar.append("")
    if yaqin:
        qatorlar.append("⚠️ <b>Yaqinlashmoqda:</b>")
        for i in yaqin:
            kun = "bugun" if i.days_left == 0 else f"{i.days_left} kun"
            qatorlar.append(
                f"• {i.user_name} — {i.kind_label} ({i.due_date.isoformat()}, {kun})"
            )
        qatorlar.append("")
    qatorlar.append("Sayt → <b>Muddatlar</b> bo'limida yopish mumkin.")
    return "\n".join(qatorlar)


async def celebration_people_tick(db: AsyncSession) -> dict:
    """Bugungi tug'ilgan kun va ish yubileylarini guruhga chiqaradi
    (yangi TZ 3.14 / S-22).

    ⚠️ YANGI MEXANIZM YO'Q — mavjud `celebration` ishlatiladi: o'sha
    jadval, o'sha video, o'sha «👏 Tabriklash» tugmasi.

    Takrorlanishdan `dedupe_key` (UNIQUE) qo'riqlaydi, ya'ni cron kuniga
    necha marta ishlasa ham guruhga bitta tabrik ketadi."""
    from api.services.celebration import announce_people

    return await announce_people(db)


async def celebration_people_reminder_tick(db: AsyncSession) -> dict:
    """ERTANGI tug'ilgan kun va yubiley haqida HR ga eslatma.

    NEGA BIR KUN OLDIN: tort, sovg'a yoki oddiy e'tibor uchun vaqt
    kerak. Tabrikning o'zi ertaga avtomatik chiqadi, bu esa ODAM
    tayyorgarligi uchun.

    Xabar SHAXSIY: kimningdir tug'ilgan kunini guruhga bir kun oldin
    e'lon qilish syurprizni buzadi."""
    from sqlalchemy import select

    from api.notify import notify_user
    from api.services.celebration import people_tomorrow
    from api.services.push import Category
    from db.models import CelebrationKind, Role, User

    hodisalar = await people_tomorrow(db)
    if not hodisalar:
        return {"ok": True, "found": 0}

    qatorlar = []
    for user, kind, n in hodisalar:
        if kind == CelebrationKind.birthday.value:
            qatorlar.append(f"🎂 {user.full_name} — tug'ilgan kun")
        else:
            qatorlar.append(f"🏆 {user.full_name} — {n} yillik ish yubileyi")

    text = (
        "📅 <b>Ertaga:</b>\n"
        + "\n".join(qatorlar)
        + "\n\nTabrik guruhga ertaga avtomatik chiqadi — bu eslatma "
        "tayyorgarlik uchun."
    )
    targets = list(
        await db.scalars(
            select(User).where(
                User.role.in_((Role.hr.value, Role.boss.value, Role.dasturchi.value)),
                User.is_active.is_(True),
                User.telegram_id.isnot(None),
            )
        )
    )
    for u in targets:
        await notify_user(db, u, Category.APPROVALS, text, data={"path": "/users"})
    return {"ok": True, "found": len(hodisalar), "notified": len(targets)}


async def contract_registration_tick(db: AsyncSession) -> dict:
    """Shartnomasi ro'yxatdan o'tkazilmagan xodimlar uchun MUDDAT
    yaratadi (yangi TZ 3.28 / S-27).

    ⚠️ YANGI XABAR YO'LI QURILMAYDI. Muddat `deadlines` (S-12) ga
    yoziladi va eslatmani `deadline_tick` (S-13) yuboradi — u
    allaqachon takrorlanishni to'sadi (`reminded_at`) va bir kunga
    tushgan bandlarni bitta xabarga birlashtiradi.

    ⚠️ TAKRORLANMAYDI: xodim uchun OCHIQ muddat bo'lsa ikkinchisi
    yaratilmaydi. Belgi qo'yilgach muddat avtomatik YOPILADI."""
    from sqlalchemy import select

    from api.routers.employee_documents import REGISTRATION_GRACE_DAYS
    from api.timeutil import today_local
    from db.models import (
        Deadline,
        DeadlineKind,
        DeadlineStatus,
        DocumentType,
        EmployeeDocument,
        User,
    )

    bugun = today_local()
    ochiq = {
        d.user_id: d
        for d in await db.scalars(
            select(Deadline).where(
                Deadline.kind == DeadlineKind.contract_registration.value,
                Deadline.status == DeadlineStatus.open.value,
            )
        )
    }
    belgilangan = {
        d.user_id
        for d in await db.scalars(
            select(EmployeeDocument).where(
                EmployeeDocument.deleted_at.is_(None),
                EmployeeDocument.doc_type == DocumentType.contract.value,
                EmployeeDocument.registered_at.isnot(None),
            )
        )
    }

    yaratildi = yopildi = 0
    for u in await db.scalars(
        select(User).where(User.is_active.is_(True), User.hire_date.isnot(None))
    ):
        kechikish = (bugun - u.hire_date).days
        band = ochiq.get(u.id)

        if u.id in belgilangan:
            #  Belgi qo'yilgan — ochiq muddat bo'lsa yopamiz.
            if band is not None:
                band.status = DeadlineStatus.done.value
                yopildi += 1
            continue

        if kechikish < REGISTRATION_GRACE_DAYS or band is not None:
            continue

        db.add(
            Deadline(
                user_id=u.id,
                kind=DeadlineKind.contract_registration.value,
                #  Muddat — ishga qabul + ruxsat etilgan kunlar. O'tib
                #  ketgan bo'lsa `deadline_tick` uni «muddati o'tgan»
                #  bo'limida ko'rsatadi.
                due_date=u.hire_date + timedelta(days=REGISTRATION_GRACE_DAYS),
                note="Shartnoma davlat ro'yxatidan o'tkazilmagan",
                status=DeadlineStatus.open.value,
            )
        )
        yaratildi += 1

    if yaratildi or yopildi:
        await db.commit()
    return {"ok": True, "created": yaratildi, "closed": yopildi}


async def lead_source_tick(db: AsyncSession) -> dict:
    """Lid manbasini byudjet bilan to'ldirish (voronka 2-bosqich).

    Sekin ataylab: manba faqat `GET /lead/{id}` da bo'lgani uchun har lid
    bitta CRM so'roviga tushadi. Tick'da 20 ta -> soatiga ~240 ta, ya'ni
    Uysot limitining kichik ulushi."""
    from api.services import lead_source

    return await lead_source.enrich_tick(db)


async def advance_reminder_tick(db: AsyncSession) -> dict:
    """Avans taklifiga javob bermaganlarga BITTA takroriy eslatma (C-05).

    Har soatda chaqirilishi mumkin — servis o'zi sozlamadagi
    `reminder_time` ni tekshiradi va har xodimga oyiga bir marta
    yuboradi (`reminded_at` + `outbox.dedupe_key` — ikki qatlam)."""
    from api.services.advance_bot import reminder_tick

    return await reminder_tick(db)


async def advance_day_tick(db: AsyncSession) -> dict:
    """Avans kuni e'loni (Avans TZ B-04).

    Kuniga bir marta chaqirilishi yetadi. Ichida `>=` semantikasi bor —
    cron kechiksa ham xabar tushadi; takror yuborishdan `outbox`
    `dedupe_key` qo'riqlaydi (oyiga bir marta)."""
    from api.services import advance_day

    return await advance_day.tick(db)


async def outbox_tick(db: AsyncSession) -> dict:
    """Chiquvchi xabarlar navbatini yuboradi (Avans TZ B-03).

    Har daqiqada chaqirilishi mo'ljallangan. Bir tick'da eng ko'pi bilan
    `outbox.BATCH_SIZE` xabar — Telegram rate-limitiga urilmaslik uchun;
    qolgani keyingi tick'da ketadi.

    IKKI JARAYON XAVFSIZ: navbatdan olish atomar `UPDATE ... WHERE
    status='pending'` bilan bo'ladi (production cron ikki nusxada
    ishlaydi)."""
    from api.services import outbox

    return await outbox.tick(db)


async def celebration_tick(db: AsyncSession) -> dict:
    """Tashrif/shartnoma tabriklarini guruhga e'lon qilish — ZAXIRA yo'l.

    Asosiy yo'l — Uysot webhook'i (`uysot_webhook.process_log_entry` voqealarni
    yozgach darhol chaqiradi). Bu tick webhook jim qolgan yoki voqeani
    diff-skaner topgan holat uchun. Yuborilganini `celebration_posts`
    UNIQUE cheklovi eslab qoladi, shuning uchun ikki yo'l bir-birini
    takrorlamaydi."""
    from api.services import celebration

    return await celebration.announce_pending(db)


async def knowledge_tick(db: AsyncSession) -> dict:
    """Draft bilim yozuvlarini chegaralangan AI to'plamida qayta ishlaydi.

    Draft bo'lmasa — YENGIL no-op: AI servisi umuman import qilinmaydi
    (import funksiya ichida, aynan shu sabab)."""
    pending = await db.scalar(
        select(func.count())
        .select_from(KnowledgeEntry)
        .where(KnowledgeEntry.status == KnowledgeStatus.draft.value)
    )
    if not pending:
        return {"processed": 0, "remaining": 0}
    from api.services import knowledge as svc

    return await svc.process_batch(db)


async def get_group_config(db: AsyncSession) -> GroupPostConfig:
    """Guruhga yuborish sozlamasi (yagona qator, id=1) — yo'q bo'lsa yaratadi."""
    cfg = await db.get(GroupPostConfig, 1)
    if cfg is None:
        cfg = GroupPostConfig(id=1, post_hour=19, post_minute=10)
        db.add(cfg)
        await db.commit()
        await db.refresh(cfg)
    return cfg


async def group_digest_tick(db: AsyncSession) -> dict:
    """Kunlik lid digestini guruhga yuboradi (vaqti kelgan bo'lsa).

    `>=` semantikasi ATAYLAB: cron aynan sozlangan daqiqani o'tkazib yuborsa
    ham (restart, kechikish) keyingi tick'da baribir yuboriladi;
    `last_posted_date` qo'riqchisi bir kunda ikki marta yuborilishdan
    saqlaydi.

    HAR DAQIQA chaqiriladi — shuning uchun vaqti kelmagan holat imkon qadar
    arzon: faqat bitta `SELECT` va sana solishtiruvi."""
    cfg = await get_group_config(db)
    now = datetime.now(TASHKENT_TZ)
    today = now.date()
    due = (now.hour, now.minute) >= (cfg.post_hour, cfg.post_minute)
    if not (due and cfg.last_posted_date != today):
        return {"fired": False, "time": f"{cfg.post_hour:02d}:{cfg.post_minute:02d}"}

    from api.services.daily_digest import send_daily_digest

    result = await send_daily_digest(db)
    cfg.last_posted_date = today
    # Digest ko'rsatgan jami raqamlar — ertalabki "kecha yakuni" tuzatish
    # xabari (send_yesterday_correction) yakuniy sonlarni shu bilan
    # solishtiradi.
    totals = result.get("totals") or {}
    cfg.last_posted_calls = totals.get("calls")
    cfg.last_posted_leads = totals.get("leads")
    cfg.last_posted_visits = totals.get("visits")
    cfg.last_posted_contracts = totals.get("contracts")
    await db.commit()
    return {"fired": True, **result}


async def attendance_reminder_tick(db: AsyncSession, dry_run: bool = False) -> dict:
    """Ish oynasi boshlanishiga/tugashiga 10 daqiqa, 5 daqiqa qolganda va AYNI
    VAQTIDA «Keldim»/«Ketdim» bosmaganlarga eslatma yuboradi.

    NEGA KERAK: xodim bosishni unutsa, tizimda "kelmagan" bo'lib qoladi va bu
    to'g'ridan-to'g'ri oylik jarimasiga aylanadi. Keyin uni qo'lda tuzatish
    kerak bo'ladi (`/attendance/manual`) — eslatma o'sha ishning oldini oladi.

    QAT'IY CHETLAB O'TILADI (aks holda eslatma bezor qiladi va ishonchni
    yo'qotadi):
      - dam kunidagilar (`_effective_today` -> is_working=False);
      - tasdiqlangan sababli kundagilar (`is_excused_day`);
      - allaqachon bosganlar;
      - davomat kuzatilmaydigan rol (Boshliq);
      - Telegram'ga ulanmaganlar (`telegram_id is None`).

    TAKRORLANMASLIK: tick har daqiqada ishlaydi, ya'ni "N daqiqa qoldi" sharti
    bir necha marta rost bo'ladi. `AttendanceReminder` jadvalidagi
    UNIQUE(user_id, date, kind) yozuvi HAR NUQTA bir kunda bir marta
    yuborilishini kafolatlaydi (poyga holatida ham — ikkinchi tick
    IntegrityError oladi). `kind` = "check_in_10" / "check_out_0" ko'rinishida.

    BITTA TICK'DA BITTA NUQTA: tsikl birinchi mos kelgan nuqtada to'xtaydi.
    Aks holda cron uzoq to'xtab qolgach, xodimga uchala xabar ketma-ket
    kelib, "10 daqiqa qoldi" va "boshlandi" bir vaqtda tushardi.
    """
    # `_effective_today`/`_to_min` — ish oynasi qoidasining YAGONA manbai
    # (hourly_plan). Funksiya ICHIDA import: circular importdan qochish uchun
    # va bu modul cron tomonidan import qilinganda kerak bo'lmagan qismlar
    # ko'tarilmasligi uchun.
    from api.notify import notify_user
    from api.routers.hourly_plan import _effective_today, _to_min
    from api.services.attendance import ATTENDANCE_TRACKED_ROLES, is_excused_day
    from api.services.push import Category
    from api.telegram_notify import inline_url_keyboard

    # Nuqtalar KAMAYISH tartibida ("10,5,0"): pastdagi tsikl birinchi mos
    # kelganida to'xtaydi, ya'ni eng uzoq nuqta birinchi tekshirilishi kerak.
    offsets = sorted(
        {int(x) for x in settings.attendance_reminder_offsets_min.split(",") if x.strip()},
        reverse=True,
    )
    before_catchup = settings.attendance_reminder_catchup_min

    now_local = datetime.now(TASHKENT_TZ)
    day = today_local()
    now_min = now_local.hour * 60 + now_local.minute

    users = list(
        await db.scalars(
            select(User).where(
                User.role.in_(ATTENDANCE_TRACKED_ROLES),
                User.is_active.is_(True),
                User.telegram_id.isnot(None),
            )
        )
    )

    already = {
        (r.user_id, r.kind)
        for r in await db.scalars(select(AttendanceReminder).where(AttendanceReminder.date == day))
    }

    planned: list[dict] = []
    for user in users:
        is_working, start, end = await _effective_today(db, user, day)
        if not is_working:
            continue  # dam kuni — eslatma ham, kechikish ham yo'q
        if await is_excused_day(db, user.id, day):
            continue  # sababli kun — kelishi shart emas

        att = await db.scalar(
            select(Attendance).where(Attendance.user_id == user.id, Attendance.date == day)
        )

        # ── Kelish eslatmasi: 10 daq, 5 daq qolganda va AYNI VAQTIDA ──
        if start and (att is None or att.check_in_time is None):
            delta = _to_min(start) - now_min  # ish boshlanishigacha qolgan daqiqa
            for off in offsets:
                # `off - catchup <= delta <= off`: cron bir-ikki daqiqaga
                # kechiksa ham eslatma tushib qolmaydi. Yuqori chegara `off`
                # — aks holda 10 daqiqalik eslatma 12 daqiqa qolganda kelib,
                # matndagi "10 daqiqa" yolg'on bo'lardi.
                if off - before_catchup <= delta <= off and (user.id, f"check_in_{off}") not in already:
                    planned.append({"user": user, "kind": f"check_in_{off}", "at": start, "off": off})
                    break  # bitta tick'da bitta nuqta — ketma-ket yubormaymiz

        # ── Ketish eslatmasi: faqat «Keldim» bosgan, «Ketdim» bosmaganlarga ──
        # Umuman kelmagan odamga "ketishni unutmang" deyish ma'nosiz.
        if end and att is not None and att.check_in_time is not None and att.check_out_time is None:
            delta = _to_min(end) - now_min
            for off in offsets:
                # 0-nuqtada pastki chegara YO'Q: ish tugagach ham «Ketdim»
                # bosish mumkin va kerak (aks holda `worked_minutes` yozilmay
                # qoladi), shuning uchun kechikkan tick ham yuboraveradi.
                lo = None if off == 0 else off - before_catchup
                hit = delta <= off if lo is None else lo <= delta <= off
                if hit and (user.id, f"check_out_{off}") not in already:
                    planned.append({"user": user, "kind": f"check_out_{off}", "at": end, "off": off})
                    break

    if dry_run:
        return {
            "dry_run": True,
            "planned": [
                {"user_id": p["user"].id, "full_name": p["user"].full_name, "kind": p["kind"], "at": p["at"]}
                for p in planned
            ],
        }

    sent = 0
    for p in planned:
        user, kind = p["user"], p["kind"]
        # Izni AVVAL yozamiz: yuborish sekin (Telegram+FCM) va shu orada
        # keyingi tick kelib qolsa, ikkalasi ham yuborib yuborardi.
        db.add(AttendanceReminder(user_id=user.id, date=day, kind=kind))
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            continue  # boshqa tick ulgurdi — bu yerda jim o'tamiz

        # Matn nuqtaga qarab farq qiladi: uchta bir xil xabar kelsa xodim
        # ularni o'qimay qo'yadi. 0-nuqtada "qoldi" emas, "boshlandi/tugadi".
        off, arriving = p["off"], kind.startswith("check_in")
        if off == 0:
            text = (
                f"🔔 Ish vaqti boshlandi ({p['at']}) — «Keldim» ni bosing."
                if arriving
                else f"🔔 Ish vaqti tugadi ({p['at']}) — «Ketdim» ni bosing."
            )
        else:
            text = (
                f"⏰ {off} daqiqadan keyin ish boshlanadi ({p['at']}) — «Keldim» bosishni unutmang."
                if arriving
                else f"⏰ {off} daqiqadan keyin ish tugaydi ({p['at']}) — «Ketdim» bosishni unutmang."
            )
        # UX2-W4 (C2/C7): xabar «bosing» deydi — bosadigan TUGMA ham bo'lsin;
        # force_telegram — bu eslatma jarimaga to'g'ridan-to'g'ri ta'sir qiladi,
        # push kanalida yo'qolib qolishi mumkin emas.
        btn_label = "✅ Keldim qilish" if arriving else "🚪 Ketdim qilish"
        res = await notify_user(
            db,
            user,
            Category.ATTENDANCE_REMINDER,
            text,
            reply_markup=inline_url_keyboard(
                [[(btn_label, f"{settings.frontend_url}/check-in")]]
            ),
            data={"path": "/check-in"},
            force_telegram=True,
        )
        if res["telegram"] or res["push"]:
            sent += 1

    return {"date": day.isoformat(), "candidates": len(planned), "sent": sent}


async def hourly_plan_send(db: AsyncSession) -> dict:
    """Har soat boshida: ayni damda ish vaqtida bo'lgan va normasi bor xodimlarga
    shu soat rejasini + progressni yuboradi. Ish vaqtidan tashqarida (yoki dam
    olish kunida) hech kimga yuborilmaydi. Xavfsizlik uchun default O'CHIQ
    (`settings.hourly_plan_enabled`) — haqiqiy xodimlarga xabar ketgani sabab.

    Bayroq o'chiq bo'lsa — ARZON no-op: `build_plan` umuman import qilinmaydi
    va bitta ham so'rov yuborilmaydi."""
    if not settings.hourly_plan_enabled:
        return {"sent": 0, "disabled": True}

    from api.notify import notify_user
    from api.routers.hourly_plan import _to_min, build_plan
    from api.services.push import Category

    now = datetime.now(TASHKENT_TZ)
    users = list(
        await db.scalars(
            select(User).where(
                User.role == Role.employee.value,
                User.is_active.is_(True),
                User.telegram_id.isnot(None),
            )
        )
    )
    sent = 0
    for user in users:
        plan = await build_plan(db, user, now)
        if not plan.is_working or not plan.metrics or plan.in_lunch:
            continue
        # Faqat ish oynasi ichida (rejada boshlanmagan/tugagan bo'lsa yubormaymiz)
        if plan.start_time and plan.end_time:
            now_min = now.hour * 60 + now.minute
            if now_min < _to_min(plan.start_time) or now_min >= _to_min(plan.end_time):
                continue
        result = await notify_user(
            db, user, Category.PLAN_REMINDERS, plan.text, data={"path": "/me/hourly-plan"}
        )
        # `notify_user` har doim dict qaytaradi (ilgari `send_message` xatoda
        # None berardi) — shuning uchun haqiqatan yuborilganini tekshiramiz.
        if result["push"] or result["telegram"]:
            sent += 1
    return {"sent": sent, "at": f"{now.hour:02d}:{now.minute:02d}", "date": today_local().isoformat()}


# ─────────────────────────────────────────────
# Ish kundaligi + murojaat SLA (KUNDALIK_ETIROZ_REJASI.md)
# ─────────────────────────────────────────────


async def work_log_reminder_tick(db: AsyncSession, dry_run: bool = False) -> dict:
    """«Bugun kundalikka hech narsa yozmadingiz» — ish tugashiga yaqin,
    BUGUN ISHLAGAN (check-in bosgan) va hali yozmagan xodimlarga.

    QAT'IY CHETLAB O'TILADI (davomat eslatmasi bilan bir falsafa):
      - dam kuni / sababli kundagilar;
      - bugun umuman kelmaganlar (kelmagan odamdan kundalik so'rash g'alati —
        u uchun tushuntirish xati mexanizmi bor);
      - bugun allaqachon yozganlar;
      - rahbar rollari (kundalik xodim mehnati hisoboti).

    TAKRORLANMASLIK: `attendance_reminders` UNIQUE(user_id, date, kind) izi,
    kind="work_log" — IZ AVVAL yoziladi va darhol commit qilinadi (yuborish
    sekin; keyingi tick shu orada kelib qolsa IntegrityError oladi va jim
    o'tadi). cPanel'da cron va Passenger parallel ishlashi mumkin."""
    from api.notify import notify_user
    from api.routers.hourly_plan import _effective_today, _to_min
    from api.services.attendance import is_excused_day
    from api.services.push import Category
    from db.models import WorkLogEntry

    # Eslatma oynasi: ish tugashiga 30 daqiqa qolganda ochiladi va ish
    # tugagach yana 2 soat ochiq turadi (cron uzoq to'xtasa ham eslatma
    # kech bo'lsa-da boradi; UNIQUE iz kuniga bittani kafolatlaydi).
    remind_before_end = 30
    remind_until_after_end = 120
    reminder_kind = "work_log"

    now_local = datetime.now(TASHKENT_TZ)
    day = today_local()
    now_min = now_local.hour * 60 + now_local.minute

    users = list(
        await db.scalars(
            select(User).where(
                User.role == Role.employee.value,
                User.is_active.is_(True),
                User.telegram_id.isnot(None),
            )
        )
    )

    already = {
        r.user_id
        for r in await db.scalars(
            select(AttendanceReminder).where(
                AttendanceReminder.date == day, AttendanceReminder.kind == reminder_kind
            )
        )
    }
    logged_today = {
        uid
        for uid in await db.scalars(
            select(WorkLogEntry.user_id)
            .where(WorkLogEntry.date == day, WorkLogEntry.deleted_at.is_(None))
            .distinct()
        )
    }

    planned: list[dict] = []
    for user in users:
        if user.id in already or user.id in logged_today:
            continue
        is_working, _start, end = await _effective_today(db, user, day)
        if not is_working or not end:
            continue
        if await is_excused_day(db, user.id, day):
            continue
        att = await db.scalar(
            select(Attendance).where(Attendance.user_id == user.id, Attendance.date == day)
        )
        if att is None or att.check_in_time is None:
            continue  # bugun kelmagan — kundalik so'ralmaydi
        delta = _to_min(end) - now_min
        if -remind_until_after_end <= delta <= remind_before_end:
            planned.append({"user": user, "end": end})

    if dry_run:
        return {
            "dry_run": True,
            "planned": [
                {"user_id": p["user"].id, "full_name": p["user"].full_name, "end": p["end"]}
                for p in planned
            ],
        }

    sent = 0
    for p in planned:
        user = p["user"]
        db.add(AttendanceReminder(user_id=user.id, date=day, kind=reminder_kind))
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            continue

        # force_telegram YO'Q: yozishni ilova/saytda ham qilsa bo'ladi, toifa
        # PERSONAL — ilova faol bo'lsa Telegram takrorlanmaydi.
        res = await notify_user(
            db,
            user,
            Category.WORK_LOG,
            "📝 <b>Ish kundaligi</b>\n"
            "Bugun kundalikka hech narsa yozmadingiz. Ish tugashidan oldin "
            "bugun bajargan ishlaringizni qisqacha yozib qo'ying — botdagi "
            "«📝 Ish kundaligi» tugmasi yoki ilovadagi Kundalik bo'limi orqali.",
            data={"path": "/me/work-log"},
        )
        if res["telegram"] or res["push"]:
            sent += 1

    return {"date": day.isoformat(), "candidates": len(planned), "sent": sent}


async def requests_sla_tick(db: AsyncSession, dry_run: bool = False) -> dict:
    """Javobsiz qolgan ARIZALAR: 3 kundan keyin HR ga eslatma, 5 kundan keyin
    Boshliqqa eskalatsiya.

    `appeals_sla_tick` bilan bir xil naqsh: iz ustunlari (`sla_reminded_at` /
    `escalated_at`) YUBORISHDAN OLDIN yoziladi va darhol commit qilinadi —
    cPanel'da cron ikki jarayonda ishlasa ham xabar bir marta ketadi."""
    from api.notify import notify_user
    from api.routers.requests import (
        SLA_ESCALATE_DAYS,
        SLA_REMIND_DAYS,
        _KIND_LABELS,
        _recipients,
    )
    from api.services.push import Category
    from db.models import REQUEST_OPEN_STATUSES, EmployeeRequest

    now = datetime.utcnow()
    open_items = list(
        await db.scalars(
            select(EmployeeRequest)
            .where(EmployeeRequest.status.in_(REQUEST_OPEN_STATUSES))
            .order_by(EmployeeRequest.created_at.asc())
        )
    )
    to_remind = [
        i for i in open_items
        if i.sla_reminded_at is None and i.created_at <= now - timedelta(days=SLA_REMIND_DAYS)
    ]
    to_escalate = [
        i for i in open_items
        if i.escalated_at is None and i.created_at <= now - timedelta(days=SLA_ESCALATE_DAYS)
    ]

    if dry_run:
        return {
            "dry_run": True,
            "remind": [i.id for i in to_remind],
            "escalate": [i.id for i in to_escalate],
        }

    reminded = 0
    for item in to_remind:
        item.sla_reminded_at = now
        await db.commit()
        days = (now - item.created_at).days
        for rec in await _recipients(db):
            await notify_user(
                db, rec, Category.APPEALS,
                f"⏳ <b>Javobsiz ariza</b> ({days} kun)\n"
                f"{_KIND_LABELS.get(item.kind, item.kind)} — ko'rib chiqing.",
                data={"path": "/requests"},
            )
        reminded += 1

    escalated = 0
    bosses = list(
        await db.scalars(
            select(User).where(
                User.role == Role.boss.value,
                User.is_active.is_(True),
                User.telegram_id.isnot(None),
            )
        )
    )
    for item in to_escalate:
        item.escalated_at = now
        await db.commit()
        days = (now - item.created_at).days
        for boss in bosses:
            await notify_user(
                db, boss, Category.APPEALS,
                f"🚨 <b>Ariza {days} kundan beri javobsiz</b>\n"
                f"{_KIND_LABELS.get(item.kind, item.kind)}.",
                data={"path": "/requests"},
            )
        escalated += 1

    return {"reminded": reminded, "escalated": escalated, "open": len(open_items)}


async def appeals_sla_tick(db: AsyncSession, dry_run: bool = False) -> dict:
    """Javobsiz qolgan murojaatlar: 3 kundan keyin qabul qiluvchiga eslatma,
    5 kundan keyin Boshliqqa eskalatsiya.

    TAKRORLANMASLIK: `sla_reminded_at` / `escalated_at` iz ustunlari — iz
    YUBORISHDAN OLDIN yoziladi va darhol commit qilinadi."""
    from api.notify import notify_user
    from api.routers.appeals import (
        SLA_ESCALATE_DAYS,
        SLA_REMIND_DAYS,
        _KIND_LABELS,
        _TOPIC_LABELS,
        _recipients,
    )
    from api.services.push import Category
    from db.models import APPEAL_OPEN_STATUSES, Appeal

    now = datetime.utcnow()
    remind_before = now - timedelta(days=SLA_REMIND_DAYS)
    escalate_before = now - timedelta(days=SLA_ESCALATE_DAYS)

    open_items = list(
        await db.scalars(
            select(Appeal)
            .where(Appeal.status.in_(APPEAL_OPEN_STATUSES))
            .order_by(Appeal.created_at.asc())
        )
    )
    to_remind = [i for i in open_items if i.sla_reminded_at is None and i.created_at <= remind_before]
    to_escalate = [i for i in open_items if i.escalated_at is None and i.created_at <= escalate_before]

    if dry_run:
        return {
            "dry_run": True,
            "remind": [i.id for i in to_remind],
            "escalate": [i.id for i in to_escalate],
        }

    reminded = 0
    for item in to_remind:
        item.sla_reminded_at = now
        await db.commit()
        days = (now - item.created_at).days
        for rec in await _recipients(db, item):
            await notify_user(
                db, rec, Category.APPEALS,
                f"⏳ <b>Javobsiz murojaat</b> ({days} kun)\n"
                f"{_KIND_LABELS[item.kind]} — {_TOPIC_LABELS.get(item.topic, item.topic)}. "
                "Iltimos, ko'rib chiqing.",
                data={"path": "/appeals"},
            )
        reminded += 1

    escalated = 0
    bosses = list(
        await db.scalars(
            select(User).where(
                User.role == Role.boss.value,
                User.is_active.is_(True),
                User.telegram_id.isnot(None),
            )
        )
    )
    for item in to_escalate:
        item.escalated_at = now
        await db.commit()
        days = (now - item.created_at).days
        for boss in bosses:
            await notify_user(
                db, boss, Category.APPEALS,
                f"🚨 <b>Murojaat {days} kundan beri javobsiz</b>\n"
                f"{_KIND_LABELS[item.kind]} — {_TOPIC_LABELS.get(item.topic, item.topic)} "
                f"(kimga: {item.recipient_role}).",
                data={"path": "/appeals"},
            )
        escalated += 1

    return {"reminded": reminded, "escalated": escalated, "open": len(open_items)}
