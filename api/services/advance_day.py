"""Avans kuni e'loni — cron va takroriylik qo'riqchisi (Avans TZ B-04).

NIMA QILADI
───────────
Oyning belgilangan kunida (sozlamadagi `advance_day`) har bir mos xodimga
«bugun avans kuni, sizga N so'mgacha mumkin» degan xabar navbatga
qo'yiladi. Xabarni C blokdagi bot oqimi tugmalar bilan boyitadi; bu
modul FAQAT kimga va qancha degan savolga javob beradi.

UCH QARORI VA SABABI
────────────────────
1. **`>=` semantikasi, `==` emas.** Cron o'tkazib yuborilishi mumkin
   (deploy, server o'chishi, `advance_day=31` bo'lgan qisqa oy). `==`
   bo'lsa xabar O'SHA OY UMUMAN ketmasdi va buni hech kim sezmasdi.
   `>=` bilan kechikkan cron baribir xabarni yetkazadi.
2. **Takroriylik qo'riqchisi — `outbox.dedupe_key`.** `>=` semantikasi
   xabarni oyning qolgan HAR KUNI qayta yuborishga urinadi, shuning
   uchun qo'riqchi SHART. Alohida jadval qurilmadi: `dedupe_key`
   («advance_day:2026-08:42») UNIQUE va aynan shu ishni bajaradi.
3. **Chegara xabar bilan birga saqlanadi.** `payload.limit` — keyin
   «xodim qanday summa ko'rgan edi?» degan savolga javob beradi va
   C blokdagi tugma bosilganda qayta hisoblashsiz ishlatiladi.

KIMGA YUBORILMAYDI (TZ ro'yxati)
────────────────────────────────
· ishdan bo'shash arizasi bergan (ochiq holatda) — pul so'rovi
  bilan bo'shash jarayoni chalkashmasin;
· chegarasi 0 (ta'tilda, stavkasiz, davr qulflangan, …);
· chegarasi `min_amount` dan past — mayda summa uchun butun oqimni
  ishga tushirishning ma'nosi yo'q;
· botni ishga tushirmagan yoki `telegram_id` yo'q — xabar baribir
  yetib bormaydi.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import delete as _delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.services.advance import limit_for, resolve_advance_settings
from api.services.advance_bot import keyboard as advance_keyboard
from api.services.outbox import enqueue
from api.timeutil import today_local
from db.models import (
    REQUEST_OPEN_STATUSES,
    AdvanceAnnouncement,
    AuditLog,
    Outbox,
    OutboxStatus,
    AdvanceResponse,
    AdvanceResponseState,
    EmployeeRequest,
    PayrollAdjustmentStatus,
    RequestKind,
    Role,
    User,
)

KIND = "advance_day"
# Qo'lda e'lon — OGOHLANTIRISH xabari (summasiz, tugmasiz). Taklif
# `KIND` bilan alohida ketadi, shuning uchun turi ham alohida:
# hisobotda «e'lon» va «taklif» aralashmasin.
KIND_NOTICE = "advance_notice"

# Avans e'loni FAQAT shu rollarga — payroll qamrovi bilan bir xil.
TRACKED_ROLES = (Role.employee.value, Role.rop.value, Role.hr.value)


def dedupe_key(period: str, user_id: int) -> str:
    """«Oyiga bir marta» kafolati. Formatni O'ZGARTIRMANG — o'zgartirilsa
    o'sha oyda xabar IKKINCHI marta ketadi."""
    return f"{KIND}:{period}:{user_id}"


async def _resigning_user_ids(db: AsyncSession) -> set[int]:
    """Ochiq ishdan bo'shash arizasi bergan xodimlar."""
    rows = await db.scalars(
        select(EmployeeRequest.user_id).where(
            EmployeeRequest.kind == RequestKind.resignation.value,
            EmployeeRequest.status.in_(REQUEST_OPEN_STATUSES),
        )
    )
    return set(rows)


def _text(full_name: str, limit: float, period: str) -> str:
    """Avans kuni xabari — TZ 1-bo'limidagi namuna bo'yicha.

    Uch qoida (hammasi TZ dan):
    · foiz EMAS, aniq summa — «oylikning 40%i» degan matn HR bilan
      bahsga olib kelardi;
    · eslatma ohangi, taklif emas — «Qancha avans olasiz?» degan
      savol avansni odatga aylantiradi (TZ 4-bo'lim);
    · nima qilish kerakligi AYTILADI — tugma bor, lekin xodim
      summani shunchaki yozishi ham mumkinligini bilishi kerak."""
    summa = f"{int(round(limit)):,}".replace(",", " ")
    return (
        f"💰 <b>Bugun — avans kuni</b>\n\n"
        f"{full_name}, siz bugun <b>{summa} so'm</b>gacha avans olishingiz mumkin.\n"
        f"Kerak bo'lsa summani yozing, kerak bo'lmasa «Kerak emas» tugmasini bosing.\n\n"
        f"<i>Bu summa {period} oyligingizdan ayiriladi. Majburiy emas.</i>"
    )


async def tick(db: AsyncSession, on_date: date | None = None) -> dict:
    """Cron chaqiruvi. Bugun avans kunimi va kimga xabar kerak.

    ⚠️ QIMMAT: har xodim uchun `limit_for()` (ichida `build_payslip`)
    chaqiriladi. Aynan shuning uchun cron ichida bajariladi — so'rov
    ichida emas. Oyiga BIR marta ishlaydi: qo'riqchi tufayli keyingi
    kunlar tick'i xodimlar ro'yxatiga umuman yetib bormaydi."""
    on_date = on_date or today_local()
    period = on_date.strftime("%Y-%m")

    users = list(
        await db.scalars(
            select(User).where(
                User.role.in_(TRACKED_ROLES),
                User.is_active.is_(True),
                User.telegram_id.isnot(None),
                User.bot_started.is_(True),
            )
        )
    )
    if not users:
        return {"date": on_date.isoformat(), "queued": 0, "reason": "mos xodim yo'q"}

    # ⚠️ D-01: shu davr uchun HR QO'LDA e'lon qilgan bo'lsa, avans kuni
    # SOZLAMADAN emas, E'LONDAN olinadi. Ogohlantirish xabari
    # allaqachon ketgan; bu yerda faqat TAKLIF yuboriladi va u
    # e'londagi sanadan boshlab ketadi.
    ann_row = await db.scalar(
        select(AdvanceAnnouncement)
        .where(AdvanceAnnouncement.period == period)
        .order_by(AdvanceAnnouncement.id.desc())
    )

    # E'lon bo'lsa — avans kuni O'SHA e'londagi sana (TZ 3-bo'lim:
    # «20-dan 23-ga ko'chirildi» bo'lsa taklif 23-kuni ketadi).
    override_day = ann_row.advance_date.day if ann_row is not None else None

    resigning = await _resigning_user_ids(db)
    queued = 0
    skipped = {"kun kelmagan": 0, "sozlama yo'q": 0, "ishdan bo'shmoqda": 0,
               "chegara 0": 0, "eng kam summadan past": 0, "allaqachon yuborilgan": 0}

    for user in users:
        settings = await resolve_advance_settings(db, user)
        if settings is None:
            # Sozlanmagan tizim xodimga pul taklif qilmasin (B-01 qoidasi).
            skipped["sozlama yo'q"] += 1
            continue
        # `>=` — cron kechiksa ham xabar tushadi (TZ talabi).
        if on_date.day < (override_day or settings.advance_day):
            skipped["kun kelmagan"] += 1
            continue
        if user.id in resigning:
            skipped["ishdan bo'shmoqda"] += 1
            continue

        info = await limit_for(db, user, on_date=on_date, period=period)
        if info.limit <= 0:
            skipped["chegara 0"] += 1
            continue
        if settings.min_amount is not None and info.limit < float(settings.min_amount):
            skipped["eng kam summadan past"] += 1
            continue

        row = await enqueue(
            db,
            chat_id=user.telegram_id,
            kind=KIND,
            text=_text(user.full_name, info.limit, period),
            # C-01: tugmalar. `callback_data` da DAVR bor — o'tgan oyning
            # xabari bosilsa chalkashmasin.
            reply_markup=advance_keyboard(period),
            dedupe_key=dedupe_key(period, user.id),
        )
        if row is None:
            skipped["allaqachon yuborilgan"] += 1
            continue
        # Chegarani xabar bilan birga saqlaymiz — C blokdagi tugma
        # bosilganda qayta hisoblash shart bo'lmasin va «xodim qanday
        # summa ko'rgan edi?» savoliga javob qolsin.
        row.payload = {**row.payload, "limit": info.limit, "period": period,
                       "user_id": user.id}

        # C-01/C-05: munosabat yozuvi. Bu qator bo'lmasa takroriy eslatma
        # (C-05) kimga yuborilishini bila olmasdi — «javob bermaganlar»
        # ro'yxati aynan shu jadvaldan olinadi.
        resp = await db.scalar(
            select(AdvanceResponse).where(
                AdvanceResponse.user_id == user.id, AdvanceResponse.period == period
            )
        )
        if resp is None:
            db.add(
                AdvanceResponse(
                    user_id=user.id,
                    period=period,
                    state=AdvanceResponseState.offered.value,
                    offered_limit=info.limit,
                )
            )
        else:
            resp.offered_limit = info.limit
        queued += 1

    await db.commit()
    return {
        "date": on_date.isoformat(),
        "period": period,
        "queued": queued,
        "skipped": {k: v for k, v in skipped.items() if v},
    }


async def _queue_offers(db: AsyncSession, period: str, on_date: date) -> int:
    """Taklif xabarlarini navbatga qo'yadi — `tick` bilan AYNAN bir xil
    qoidalar bo'yicha.

    Qo'lda e'lon sanasi allaqachon kelgan bo'lsa shu funksiya darhol
    chaqiriladi: xodim «bugun avans kuni» degan xabarni olib, summani
    ertagagacha kutib o'tirmasin."""
    res = await tick(db, on_date=on_date)
    return int(res.get("queued", 0))


async def announce_manually(
    db: AsyncSession,
    actor: User,
    advance_date: date,
    note: str | None = None,
) -> dict:
    """HR qo'lda avans kunini e'lon qiladi (D-01).

    Sozlamadagi `advance_day` ga tegilmaydi — u KEYINGI oylarga ham
    ta'sir qilardi, bu esa faqat shu oyga tegishli bir martalik qaror.

    «IKKI MARTA E'LON QILINSA OXIRGISI KUCHDA»: yangi e'lon eski
    e'londan qolgan HALI YUBORILMAGAN xabarlarni navbatdan olib
    tashlaydi. Allaqachon yuborilganini qaytarib bo'lmaydi — shuning
    uchun yangi xabarda sana aniq aytiladi va xodim oxirgisiga
    qaraydi.

    ⚠️ BU XABARDA SUMMA YO'Q (TZ 3-bo'lim namunasi). E'lon faqat
    «avans kuni qachon» degan savolga javob beradi; qancha olish
    mumkinligi O'SHA KUNI alohida taklif xabari bilan keladi.
    Sabab: e'lon oy boshida qilinishi mumkin, o'shanda hisoblangan
    chegara avans kuniga kelib O'ZGARADI (ishlangan kun ortadi).
    Summani oldindan aytish — keyin uni qaytarib olish demakdir."""
    period = advance_date.strftime("%Y-%m")

    # Eski e'londan qolgan yuborilmagan xabarlarni tozalaymiz — ham
    # ogohlantirishni, ham taklifni («oxirgisi kuchda»).
    await db.execute(
        _delete(Outbox).where(
            Outbox.kind.in_((KIND, KIND_NOTICE)),
            Outbox.status == OutboxStatus.pending.value,
            Outbox.dedupe_key.like(f"%:{period}:%"),
        )
    )
    await db.flush()

    ann = AdvanceAnnouncement(
        period=period, advance_date=advance_date, note=(note or "").strip() or None,
        sent_by=actor.id,
    )
    db.add(ann)
    await db.flush()

    users = list(
        await db.scalars(
            select(User).where(
                User.role.in_(TRACKED_ROLES),
                User.is_active.is_(True),
                User.telegram_id.isnot(None),
                User.bot_started.is_(True),
            )
        )
    )
    # Sana ko'chirilganmi — xabar matni shunga qarab boshqacha.
    settings_any = await resolve_advance_settings(db, users[0]) if users else None
    moved = settings_any is not None and advance_date.day != settings_any.advance_day

    resigning = await _resigning_user_ids(db)
    queued = 0
    for user in users:
        settings = await resolve_advance_settings(db, user)
        if settings is None or user.id in resigning:
            continue

        row = await enqueue(
            db,
            chat_id=user.telegram_id,
            kind=KIND_NOTICE,
            text=_manual_text(advance_date, ann.note, moved),
            # E'lon `id` si kalitda: qayta e'lon qilinsa YANGI xabar
            # ketadi (eskisi yuqorida navbatdan olib tashlangan).
            dedupe_key=f"{KIND_NOTICE}:{period}:{user.id}:a{ann.id}",
        )
        if row is None:
            continue
        queued += 1

    ann.recipients = queued

    # Sana ALLAQACHON kelgan bo'lsa (HR o'sha kuni yoki keyin e'lon
    # qildi) — taklifni ham darhol yuboramiz. Aks holda xodim
    # «bugun avans kuni» degan xabarni olib, summani ertagagacha
    # kutib o'tirardi.
    if advance_date <= today_local():
        await _queue_offers(db, period, advance_date)
    db.add(
        AuditLog(
            actor_id=actor.id,
            action="advance_announced",
            target_user_id=None,
            before=None,
            after={"period": period, "advance_date": advance_date.isoformat(),
                   "note": ann.note, "recipients": queued},
        )
    )
    await db.commit()
    return {"period": period, "advance_date": advance_date.isoformat(),
            "recipients": queued, "announcement_id": ann.id}


def _manual_text(advance_date: date, note: str | None, moved: bool) -> str:
    """Qo'lda e'lon — OGOHLANTIRISH xabari (TZ 3-bo'lim namunasi).

    ⚠️ Bu TAKLIF EMAS va unda summa YO'Q. Sabab TZ namunasida aniq:
    e'lon faqat «avans kuni qachon» degan savolga javob beradi, qancha
    olish mumkinligi esa O'SHA KUNI alohida xabar bilan keladi.

    Nega shunday: e'lon oyning boshida qilinishi mumkin, o'shanda
    hisoblangan chegara avans kuniga kelib O'ZGARADI (ishlangan kun
    ortadi, boshqa ushlanma tushadi). Summani oldindan aytish —
    keyin uni qaytarib olish demakdir."""
    oylar = ("yanvar", "fevral", "mart", "aprel", "may", "iyun",
             "iyul", "avgust", "sentabr", "oktabr", "noyabr", "dekabr")
    sana = f"{advance_date.day}-{oylar[advance_date.month - 1]}"
    qatorlar = ["📢 <b>Diqqat</b>", ""]
    if moved:
        qatorlar.append(f"Bu oy avans kuni <b>{sana}</b>ga ko'chirildi.")
    else:
        qatorlar.append(f"Bu oy avans kuni — <b>{sana}</b>.")
    qatorlar.append(
        "O'sha kuni sizga qancha avans olishingiz mumkinligi haqida xabar keladi."
    )
    if note:
        qatorlar += ["", note]
    return "\n".join(qatorlar)
