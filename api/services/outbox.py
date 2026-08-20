"""Chiquvchi xabarlar navbati (Avans TZ B-03) — ⭐ umumiy poydevor.

NEGA KERAK
──────────
Hozir xabarlar SO'ROV ICHIDA yuboriladi: `await notify_user(...)` HTTP
so'rov tugashidan oldin Telegramga chiqadi. Uch oqibati bor:

1. **Sayt qotadi.** cPanel/Passenger'da konkurentlik = 1 (xotiradagi
   `sayt-qotishi-passenger` tahlili). Telegram 3 soniya javob bermasa,
   o'sha 3 soniya davomida BUTUN sayt kutadi.
2. **Xabar yo'qoladi.** `send_message` xatoda `None` qaytaradi va tamom —
   qayta urinish yo'q, iz ham yo'q.
3. **Rate-limit.** 50 xodimga birdan xabar yuborish Telegram cheklovига
   tushadi va bir qismi jimgina yo'qoladi.

Navbat orqali: so'rov xabarni BAZAGA yozadi (millisekund) va darhol javob
qaytaradi; yuborishni cron o'z jarayonida, cheklangan tezlikda bajaradi.

IKKI JARAYON MUAMMOSI
─────────────────────
Productionда cron IKKI nusxada ishlaydi. Navbatdan olish ATOMAR:
`UPDATE ... SET status='sending', claimed_by=:token WHERE status='pending'`
— keyin jarayon FAQAT o'z tokeni bilan belgilangan qatorlarni oladi.
Ikkinchi jarayon o'sha qatorlarni endi `pending` holatda ko'rmaydi.

Jarayon yuborish o'rtasida o'lib qolsa qator `sending` bo'lib osilib
qolardi — `_reclaim_stale()` uni belgilangan vaqtdan keyin `pending` ga
qaytaradi.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.telegram_notify import send_message
from db.models import Outbox, OutboxStatus, Role, User

# Bir tick'da yuboriladigan xabar soni. Telegram bir chat uchun ~1 msg/sek,
# umumiy ~30 msg/sek ruxsat beradi; 20 — cron har daqiqada ishlaganda
# xavfsiz va 50 xodimga xabar 3 daqiqada yetib boradi.
BATCH_SIZE = 20

# Shundan keyin urinish TO'XTAYDI. Uch marta muvaffaqiyatsiz bo'lgan xabar
# odatda kod yoki sozlama xatosi — cheksiz urinish faqat jurnalni to'ldiradi.
MAX_ATTEMPTS = 3

# `sending` da osilib qolgan qatorni qaytarib olish muddati (jarayon o'lgan).
STALE_MINUTES = 10


async def enqueue(
    db: AsyncSession,
    chat_id: int,
    kind: str,
    text: str,
    reply_markup: dict | None = None,
    scheduled_at: datetime | None = None,
    dedupe_key: str | None = None,
) -> Outbox | None:
    """Xabarni navbatga qo'yadi. `commit` QILMAYDI — chaqiruvchi uni o'z
    tranzaksiyasi bilan yakunlaydi (xabar yozilib, asosiy o'zgarish
    qaytarilgan holat bo'lmasin).

    `dedupe_key` berilgan va shunday kalit allaqachon bo'lsa — `None`
    qaytaradi va HECH NARSA yozmaydi. Bu «oyiga bir marta» kabi
    qo'riqchilar uchun: chaqiruvchi tekshiruv yozishi shart emas."""
    if dedupe_key:
        exists = await db.scalar(select(Outbox.id).where(Outbox.dedupe_key == dedupe_key))
        if exists is not None:
            return None

    row = Outbox(
        chat_id=chat_id,
        kind=kind,
        payload={"text": text, **({"reply_markup": reply_markup} if reply_markup else {})},
        status=OutboxStatus.pending.value,
        scheduled_at=scheduled_at or datetime.utcnow(),
        dedupe_key=dedupe_key,
    )
    db.add(row)
    try:
        await db.flush()
    except IntegrityError:
        # Poyga: ikki jarayon bir vaqtda bir xil `dedupe_key` bilan
        # qo'ydi. UNIQUE cheklov ushladi — bu XATO EMAS, aynan
        # kutilgan natija (xabar bir marta ketadi).
        await db.rollback()
        return None
    return row


async def _reclaim_stale(db: AsyncSession) -> int:
    """`sending` da qolib ketgan qatorlarni `pending` ga qaytaradi.

    Jarayon yuborish o'rtasida o'lsa (deploy, OOM, cron timeout) qator
    abadiy `sending` bo'lib qolardi va xabar hech qachon yetib bormasdi."""
    chegara = datetime.utcnow() - timedelta(minutes=STALE_MINUTES)
    res = await db.execute(
        update(Outbox)
        .where(
            Outbox.status == OutboxStatus.sending.value,
            Outbox.claimed_at < chegara,
        )
        .values(status=OutboxStatus.pending.value, claimed_by=None, claimed_at=None)
    )
    return res.rowcount or 0


async def _claim(db: AsyncSession, limit: int) -> tuple[str, list[Outbox]]:
    """Navbatdan `limit` tagacha xabarni ATOMAR band qiladi.

    `UPDATE ... WHERE status='pending'` — ikkinchi jarayon o'sha qatorlarni
    endi `pending` holatda ko'rmaydi, ya'ni bitta xabar ikki marta
    yuborilmaydi. `LIMIT` to'g'ridan-to'g'ri UPDATE'da ishlamaydi
    (SQLite), shuning uchun ichki `SELECT` bilan."""
    token = uuid.uuid4().hex[:32]
    now = datetime.utcnow()

    ids_q = (
        select(Outbox.id)
        .where(
            Outbox.status == OutboxStatus.pending.value,
            Outbox.scheduled_at <= now,
            Outbox.attempts < MAX_ATTEMPTS,
        )
        .order_by(Outbox.scheduled_at, Outbox.id)
        .limit(limit)
    )
    ids = list(await db.scalars(ids_q))
    if not ids:
        return token, []

    await db.execute(
        update(Outbox)
        .where(Outbox.id.in_(ids), Outbox.status == OutboxStatus.pending.value)
        .values(
            status=OutboxStatus.sending.value,
            claimed_by=token,
            claimed_at=now,
            attempts=Outbox.attempts + 1,
        )
    )
    await db.commit()

    rows = list(
        await db.scalars(
            select(Outbox).where(
                Outbox.claimed_by == token, Outbox.status == OutboxStatus.sending.value
            )
        )
    )
    return token, rows


async def tick(db: AsyncSession, limit: int = BATCH_SIZE) -> dict:
    """Cron chaqiruvi — navbatdan bir necha xabarni yuboradi.

    Natija: yuborilgan/xato/qaytarib olingan sonlari. Xato bo'lsa
    `attempts` allaqachon oshirilgan (band qilishda), ya'ni jarayon
    o'lib qolsa ham cheksiz urinish bo'lmaydi."""
    reclaimed = await _reclaim_stale(db)
    if reclaimed:
        await db.commit()

    token, rows = await _claim(db, limit)
    sent = failed = 0
    exhausted: list[Outbox] = []

    for row in rows:
        payload = row.payload or {}
        try:
            ok = await send_message(
                row.chat_id, payload.get("text", ""), payload.get("reply_markup")
            )
            xato = None if ok is not None else "Telegram javob bermadi"
        except Exception as e:  # noqa: BLE001 — sabab matn sifatida saqlanadi
            ok, xato = None, f"{type(e).__name__}: {e}"

        if xato is None:
            row.status = OutboxStatus.sent.value
            row.sent_at = datetime.utcnow()
            row.last_error = None
            sent += 1
        else:
            row.last_error = xato[:500]
            failed += 1
            if row.attempts >= MAX_ATTEMPTS:
                # Urinishlar tugadi — qator `failed` bo'ladi va boshqa
                # olinmaydi. HR ga xabar beriladi: jim yo'qolgan xabar
                # eng yomon holat.
                row.status = OutboxStatus.failed.value
                exhausted.append(row)
            else:
                row.status = OutboxStatus.pending.value
            row.claimed_by = None
            row.claimed_at = None
    await db.commit()

    if exhausted:
        await _alert_hr(db, exhausted)

    return {"sent": sent, "failed": failed, "reclaimed": reclaimed, "claimed": len(rows)}


async def _alert_hr(db: AsyncSession, rows: list[Outbox]) -> None:
    """Yuborib bo'lmagan xabarlar haqida HR/Dasturchiga ogohlantirish.

    ⚠️ Bu xabar ATAYLAB navbatdan O'TMAYDI, to'g'ridan-to'g'ri yuboriladi:
    navbat ishlamayotgani haqidagi ogohlantirishni o'sha navbatga
    qo'yish — uni ham yo'qotish demakdir. Hajmi kichik (nosozlik kamdan
    kam), shuning uchun so'rovni sekinlashtirmaydi."""
    kimlar = list(
        await db.scalars(
            select(User).where(
                User.role.in_((Role.hr.value, Role.dasturchi.value)),
                User.is_active.is_(True),
                User.telegram_id.isnot(None),
            )
        )
    )
    if not kimlar:
        return
    turlar = ", ".join(sorted({r.kind for r in rows}))
    sabab = rows[0].last_error or "noma'lum"
    matn = (
        f"⚠️ <b>Xabar navbatida nosozlik</b>\n\n"
        f"{len(rows)} ta xabar {MAX_ATTEMPTS} urinishdan keyin ham yuborilmadi.\n"
        f"Turi: {turlar}\n"
        f"Oxirgi xato: {sabab[:200]}"
    )
    for u in kimlar:
        await send_message(u.telegram_id, matn)
