"""Avans bot oqimi — tugmalar, summa kiritish va natija (Avans TZ C-01…C-05).

BUTUN MANTIQ SHU YERDA, botda emas. Bot faqat tugma bosilganini va matn
yozilganini API ga uzatadi; qaror, chegara va yozuv shu modulda. Sabab:
pul mantiqi bitta joyda tursin — bot va sayt bir xil qoidaga bo'ysunsin.

OQIM
────
  B-04 (avans kuni)  → xabar + [Summa kiritish] [Kerak emas]
  «Kerak emas»       → `declined`, takroriy eslatma YO'Q, qisqa tasdiq
  «Summa kiritish»   → `waiting_input` (BAZADA, 2 soat), «summani yozing»
  matn (raqam)       → chegara QAYTA hisoblanadi → so'rov yaratiladi
  Boshliq qarori     → xodimga natija xabari (rad bo'lsa SABAB bilan)

UCH NOZIK JOY
─────────────
1. **Holat bazada, FSM da emas** (C-02). Passenger jarayoni qayta ishga
   tushsa FSM yo'qolardi va xodim yozgan summa hech qayerga bormasdi.
2. **Chegara QAYTA hisoblanadi** (C-03). Xabar yuborilgandan keyin
   boshqa avans tasdiqlangan bo'lishi mumkin — eski summaga ishonish
   chegaradan oshiq pul berishga olib kelardi.
3. **`callback_data` da DAVR bor** (C-01). O'tgan oyning xabari bosilsa
   «bu xabar eskirgan» deyiladi, jimgina joriy oyga yozilmaydi.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.services.advance import limit_for, resolve_advance_settings
from api.services.outbox import enqueue
from api.timeutil import today_local
from db.models import (
    AdvanceResponse,
    AdvanceResponseState,
    PayrollAdjustment,
    PayrollAdjustmentCategory,
    PayrollAdjustmentKind,
    PayrollAdjustmentSource,
    PayrollAdjustmentStatus,
    PayrollPeriod,
    Role,
    User,
)

# «Summa kiritish» bosilgandan keyin necha vaqt raqam kutiladi. 2 soat —
# xodim xabarni ko'rib, o'ylab, keyin yozishi uchun yetarli; undan uzoq
# bo'lsa esa keyingi kunlarda tasodifan yozilgan raqam summa deb
# qabul qilinardi.
INPUT_TTL_MINUTES = 120

KIND_REQUEST = "advance_request"   # HR/Boshliqqa so'rov xabari
KIND_RESULT = "advance_result"     # xodimga natija xabari
KIND_REMINDER = "advance_reminder"  # C-05 takroriy eslatma


def _fmt(amount: float) -> str:
    return f"{int(round(amount)):,}".replace(",", " ") + " so'm"


def parse_amount(text: str) -> float | None:
    """«1 200 000», «1200000», «1.200.000 so'm», «1,2 mln» kabi matnlardan
    raqam ajratadi.

    NEGA KENG: xodim summani xohlagan ko'rinishda yozadi va «raqam
    tushunilmadi» degan javob uni to'xtatib qo'yardi. Faqat butunlay
    raqamsiz matn rad etiladi — u boshqa oqimning xabari bo'lishi
    mumkin (SkipHandler bilan o'tkaziladi)."""
    t = (text or "").strip().lower()
    if not t:
        return None

    mln = bool(re.search(r"\b(mln|million|milion)\b", t))
    # Faqat raqam, bo'sh joy, nuqta va vergul qoladi.
    tozalangan = re.sub(r"[^\d.,]", "", t)
    if not re.search(r"\d", tozalangan):
        return None

    if mln:
        # «1,2 mln» / «1.5 mln» — kasr ajratgichi
        son = tozalangan.replace(",", ".")
        # Bir nechta nuqta bo'lsa oxirgisidan boshqasi ming ajratgichi
        qismlar = son.split(".")
        if len(qismlar) > 2:
            son = "".join(qismlar[:-1]) + "." + qismlar[-1]
        try:
            return float(son) * 1_000_000
        except ValueError:
            return None

    # Ming ajratgichlarini olib tashlaymiz («1.200.000», «1,200,000»)
    raqamlar = re.sub(r"[.,]", "", tozalangan)
    if not raqamlar.isdigit():
        return None
    return float(raqamlar)


async def _get_or_create(db: AsyncSession, user_id: int, period: str) -> AdvanceResponse:
    row = await db.scalar(
        select(AdvanceResponse).where(
            AdvanceResponse.user_id == user_id, AdvanceResponse.period == period
        )
    )
    if row is None:
        row = AdvanceResponse(user_id=user_id, period=period)
        db.add(row)
        await db.flush()
    return row


def keyboard(period: str) -> dict:
    """Avans kuni xabarining tugmalari (C-01).

    `callback_data` da DAVR bor — o'tgan oyning xabari bosilsa
    chalkashmasin."""
    return {
        "inline_keyboard": [
            [
                {"text": "💵 Summa kiritish", "callback_data": f"adv:need:{period}"},
                {"text": "Kerak emas", "callback_data": f"adv:no:{period}"},
            ]
        ]
    }


async def on_callback(db: AsyncSession, telegram_id: int, action: str, period: str) -> dict:
    """Tugma bosilganda. `action`: `need` | `no`.

    Qaytadi: `{"text": "...", "clear_keyboard": bool}` — bot shuni
    ko'rsatadi va kerak bo'lsa tugmalarni olib tashlaydi."""
    user = await db.scalar(select(User).where(User.telegram_id == telegram_id))
    if user is None or not user.is_active:
        return {"text": "Foydalanuvchi topilmadi.", "clear_keyboard": True}

    joriy = today_local().strftime("%Y-%m")
    if period != joriy:
        # Eski xabar. Jimgina joriy oyga yozish — xodim kutmagan natija.
        return {
            "text": f"Bu xabar {period} oyiga tegishli va eskirgan. "
                    f"Joriy oy uchun «💵 Avanslarim» bo'limiga qarang.",
            "clear_keyboard": True,
        }

    row = await _get_or_create(db, user.id, period)

    if action == "no":
        row.state = AdvanceResponseState.declined.value
        row.input_expires_at = None
        await db.commit()
        return {
            "text": "Yaxshi, bu oy avans taklif qilinmaydi. "
                    "Fikringiz o'zgarsa «💵 Avanslarim» bo'limidan ko'rishingiz mumkin.",
            "clear_keyboard": True,
        }

    if action != "need":
        return {"text": "Noma'lum amal.", "clear_keyboard": False}

    if row.state == AdvanceResponseState.submitted.value:
        return {
            "text": "Bu oy uchun avans so'rovingiz allaqachon yuborilgan — "
                    "javobni kutib turing.",
            "clear_keyboard": True,
        }

    # Chegarani SHU PAYTDA qayta hisoblaymiz — xabar yuborilgandan beri
    # o'zgargan bo'lishi mumkin.
    info = await limit_for(db, user, period=period)
    if info.limit <= 0:
        row.state = AdvanceResponseState.declined.value
        await db.commit()
        sabab = info.reason or "chegara 0"
        return {"text": f"Hozir avans olib bo'lmaydi ({sabab}).", "clear_keyboard": True}

    row.state = AdvanceResponseState.waiting_input.value
    row.offered_limit = info.limit
    row.input_expires_at = datetime.utcnow() + timedelta(minutes=INPUT_TTL_MINUTES)
    await db.commit()
    return {
        "text": (
            f"Qancha avans kerak? Raqam bilan yozing.\n\n"
            f"Ruxsat etilgan eng katta summa: <b>{_fmt(info.limit)}</b>."
        ),
        "clear_keyboard": True,
    }


async def on_text(db: AsyncSession, telegram_id: int, text: str) -> dict:
    """Xodim matn yozganda (C-02, C-03).

    Qaytadi `{"handled": bool, "text": str | None}`. `handled=False` —
    bu xabar avans oqimiga tegishli EMAS va bot uni keyingi handlerga
    o'tkazadi (`SkipHandler`). Bu shart: aks holda yangi handler anketa
    javoblari va AI sabab matnlarini yutib yuborardi."""
    user = await db.scalar(select(User).where(User.telegram_id == telegram_id))
    if user is None or not user.is_active:
        return {"handled": False}

    joriy = today_local().strftime("%Y-%m")
    row = await db.scalar(
        select(AdvanceResponse).where(
            AdvanceResponse.user_id == user.id,
            AdvanceResponse.period == joriy,
            AdvanceResponse.state == AdvanceResponseState.waiting_input.value,
        )
    )
    if row is None:
        return {"handled": False}

    if row.input_expires_at is not None and row.input_expires_at < datetime.utcnow():
        # Muddat o'tdi — holatni bekor qilamiz va xabarni O'TKAZAMIZ.
        # Aks holda xodim ertasi kuni yozgan oddiy xabar summa deb
        # qabul qilinardi.
        row.state = AdvanceResponseState.offered.value
        row.input_expires_at = None
        await db.commit()
        return {"handled": False}

    amount = parse_amount(text)
    if amount is None:
        # Raqamsiz matn — boshqa oqimning xabari bo'lishi mumkin.
        return {"handled": False}

    return await submit(db, user, joriy, amount, row)


async def submit(
    db: AsyncSession,
    user: User,
    period: str,
    amount: float,
    row: AdvanceResponse | None = None,
) -> dict:
    """Summani tekshiradi va so'rov yaratadi (C-03, C-04)."""
    if row is None:
        row = await _get_or_create(db, user.id, period)

    period_row = await db.scalar(select(PayrollPeriod).where(PayrollPeriod.period == period))
    if period_row is not None and period_row.locked:
        return {"handled": True, "text": "Bu davr yopilgan — avans so'rab bo'lmaydi."}

    if amount <= 0:
        return {"handled": True, "text": "Summa musbat son bo'lishi kerak. Qayta yozing."}

    settings = await resolve_advance_settings(db, user)
    min_amount = float(settings.min_amount) if settings and settings.min_amount else None
    if min_amount is not None and amount < min_amount:
        return {
            "handled": True,
            "text": f"Eng kam avans summasi — {_fmt(min_amount)}. Qayta yozing.",
        }

    # ⚠️ Chegara QAYTA hisoblanadi: xabar yuborilgandan beri boshqa avans
    # tasdiqlangan bo'lishi mumkin va eski summaga ishonish chegaradan
    # oshiq pul berishga olib kelardi.
    info = await limit_for(db, user, period=period)
    if info.limit <= 0:
        row.state = AdvanceResponseState.declined.value
        await db.commit()
        sabab = info.reason or "chegara 0"
        return {"handled": True, "text": f"Hozir avans olib bo'lmaydi ({sabab})."}
    if amount > info.limit:
        # Holat `waiting_input` da QOLADI — xodim qayta yozishi mumkin.
        row.offered_limit = info.limit
        row.input_expires_at = datetime.utcnow() + timedelta(minutes=INPUT_TTL_MINUTES)
        await db.commit()
        return {
            "handled": True,
            "text": (
                f"So'ralgan summa chegaradan oshdi.\n"
                f"Ruxsat etilgan: <b>{_fmt(info.limit)}</b>\n"
                f"So'ralgan: {_fmt(amount)}\n\n"
                f"Kichikroq summa yozing."
            ),
        }

    adj = PayrollAdjustment(
        user_id=user.id,
        period=period,
        kind=PayrollAdjustmentKind.minus.value,
        amount=amount,
        reason="Bot orqali avans so'rovi",
        created_by=user.id,
        category=PayrollAdjustmentCategory.advance.value,
        status=PayrollAdjustmentStatus.pending.value,
        source=PayrollAdjustmentSource.bot.value,
    )
    db.add(adj)
    await db.flush()

    row.state = AdvanceResponseState.submitted.value
    row.input_expires_at = None
    row.adjustment_id = adj.id

    # HR/Boshliqqa xabar — OUTBOX orqali (so'rov ichida emas).
    rahbarlar = list(
        await db.scalars(
            select(User).where(
                User.role.in_((Role.hr.value, Role.boss.value, Role.dasturchi.value)),
                User.is_active.is_(True),
                User.telegram_id.isnot(None),
            )
        )
    )
    for r in rahbarlar:
        await enqueue(
            db,
            chat_id=r.telegram_id,
            kind=KIND_REQUEST,
            text=(
                f"💵 <b>Bot orqali avans so'rovi</b>\n\n"
                f"Xodim: {user.full_name}\n"
                f"Summa: {_fmt(amount)}\n"
                f"Davr: {period}\n"
                f"Chegara: {_fmt(info.limit)}\n\n"
                f"Tasdiqlash uchun saytdagi «Ish haqi → Avans» bo'limiga o'ting."
            ),
        )
    await db.commit()
    return {
        "handled": True,
        "text": (
            f"So'rovingiz yuborildi: <b>{_fmt(amount)}</b>.\n"
            f"Boshliq tasdiqlagach xabar beramiz."
        ),
    }


async def notify_decision(db: AsyncSession, adj: PayrollAdjustment) -> None:
    """Boshliq qaror qilgach xodimga natija xabari (C-04).

    ⚠️ OUTBOX orqali: qaror `decide_advance` so'rovi ichida qabul
    qilinadi va o'sha yerda Telegramga chiqish saytni qotirardi.

    FAQAT bot orqali kelgan so'rovlar uchun — HR qo'lda kiritganida
    xodimga allaqachon `decide_advance` o'zi xabar beradi va ikki
    marta yuborilmasligi kerak."""
    if adj.source != PayrollAdjustmentSource.bot.value:
        return
    user = await db.get(User, adj.user_id)
    if user is None or not user.telegram_id:
        return

    if adj.status == PayrollAdjustmentStatus.approved.value:
        matn = (
            f"✅ <b>Avans so'rovingiz tasdiqlandi</b>\n\n"
            f"Summa: {_fmt(float(adj.amount))}\n\n"
            f"Pulni kassadan olganingizda tizimda belgilanadi. "
            f"Bu summa {adj.period} oyligingizdan ayiriladi."
        )
    elif adj.status == PayrollAdjustmentStatus.rejected.value:
        sabab = (adj.decided_note or "").strip()
        matn = (
            f"❌ <b>Avans so'rovingiz rad etildi</b>\n\n"
            f"Summa: {_fmt(float(adj.amount))}\n"
            + (f"Sabab: {sabab}" if sabab else "Sabab ko'rsatilmagan.")
        )
    else:
        return

    await enqueue(db, chat_id=user.telegram_id, kind=KIND_RESULT, text=matn)


async def reminder_tick(db: AsyncSession, on_date=None) -> dict:
    """Javob bermaganlarga BITTA takroriy eslatma (C-05).

    Sozlamadagi `reminder_time` dan keyin ishlaydi va har bir xodimga
    oyiga BIR marta yuboradi (`reminded_at`). «Kerak emas» bosgan yoki
    summa kiritganlarga ketmaydi — ular javob bergan."""
    on_date = on_date or today_local()
    period = on_date.strftime("%Y-%m")

    rows = list(
        await db.scalars(
            select(AdvanceResponse).where(
                AdvanceResponse.period == period,
                AdvanceResponse.state == AdvanceResponseState.offered.value,
                AdvanceResponse.reminded_at.is_(None),
            )
        )
    )
    yuborildi = 0
    for row in rows:
        user = await db.get(User, row.user_id)
        if user is None or not user.telegram_id or not user.is_active:
            continue
        settings = await resolve_advance_settings(db, user)
        if settings is None:
            continue
        soat, daqiqa = (int(x) for x in (settings.reminder_time or "14:00").split(":"))
        hozir = datetime.now().astimezone().strftime("%H:%M")
        if (hozir < f"{soat:02d}:{daqiqa:02d}") and on_date == today_local():
            continue

        # Chegara o'zgargan bo'lishi mumkin — eslatmada YANGI raqam.
        info = await limit_for(db, user, period=period)
        if info.limit <= 0:
            continue
        r = await enqueue(
            db,
            chat_id=user.telegram_id,
            kind=KIND_REMINDER,
            text=(
                f"💵 <b>Eslatma: avans</b>\n\n"
                f"{user.full_name}, bugungi avans taklifiga javob bermadingiz.\n"
                f"Ruxsat etilgan: <b>{_fmt(info.limit)}</b>.\n\n"
                f"Kerak bo'lmasa e'tiborsiz qoldiring — boshqa eslatilmaydi."
            ),
            reply_markup=keyboard(period),
            dedupe_key=f"{KIND_REMINDER}:{period}:{row.user_id}",
        )
        # `reminded_at` HAR HOLDA qo'yiladi: `enqueue` `None` qaytarsa
        # ham (dedupe) eslatma allaqachon navbatda — ikkinchi urinish
        # kerak emas.
        row.reminded_at = datetime.utcnow()
        if r is not None:
            yuborildi += 1
    await db.commit()
    return {"period": period, "reminded": yuborildi, "candidates": len(rows)}
