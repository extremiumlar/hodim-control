"""Oylik hisobini FON rejimida bajaruvchi ish (§4.3).

NEGA BU FAYL BOR
────────────────
Production cPanel'da Passenger konkurentligi = 1 — bitta uzoq so'rov BUTUN
saytni navbatga qo'yadi. `POST /payroll/{period}/calculate` esa so'rovning
o'zida ikkita og'ir ishni bajarardi:

  1. `run_payroll` — har xodimga ~12 SQL so'rov (20 xodim ≈ 240 so'rov);
  2. har bir rahbarga `notify_user` — FCM push VA Telegram sendMessage,
     har biri tarmoq I/O, timeout 10 soniya.

Natijada tugma bosilgach ishchi 10-40 soniya band bo'lib, sayt qotardi.

YECHIM: tugma endi faqat `payroll_periods.calc_state='queued'` deb belgilaydi
(bitta yengil UPDATE), og'ir ishni esa shu modul bajaradi. U ALOHIDA JARAYONDA
ishlaydi — `scripts/cron_tick.py` in-process chaqiradi (cPanel), Docker/
scheduler rejimida esa `POST /payroll/tick` orqali. Passenger ishchisiga
umuman tegilmaydi.

⚠️ FastAPI `BackgroundTasks` ATAYLAB ISHLATILMADI: u ham O'SHA ishchi
jarayonda ishlaydi, ya'ni konkurentlik = 1 bo'lgan joyda muammoni hal
qilmaydi — faqat ko'zdan yashirardi.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import AuditLog, PayrollPeriod, Payslip, Role, User

# `running` holatida shuncha vaqtdan ko'p turgan davr — o'lgan jarayon
# qoldig'i (cron jarayoni o'ldirilgan, server qayta yuklangan va h.k.).
# Aks holda davr abadiy «hisoblanmoqda» bo'lib qolib, HR qayta bosa olmasdi.
STALE_RUNNING_MINUTES = 20


async def _reclaim_stale(db: AsyncSession) -> int:
    """Osilib qolgan `running` davrlarni `error` ga o'tkazadi."""
    chegara = datetime.utcnow() - timedelta(minutes=STALE_RUNNING_MINUTES)
    rows = list(
        await db.scalars(
            select(PayrollPeriod).where(
                PayrollPeriod.calc_state == "running",
                PayrollPeriod.calc_started_at.isnot(None),
                PayrollPeriod.calc_started_at < chegara,
            )
        )
    )
    for row in rows:
        row.calc_state = "error"
        row.calc_error = (
            f"Hisoblash {STALE_RUNNING_MINUTES} daqiqadan oshdi — jarayon uzilgan "
            f"bo'lishi mumkin. Qaytadan urinib ko'ring."
        )
    if rows:
        await db.commit()
    return len(rows)


async def payroll_tick(db: AsyncSession) -> dict:
    """Navbatdagi BITTA davrni hisoblaydi. Cron har daqiqada chaqiradi.

    Bir vaqtda faqat bitta davr — hisoblash og'ir, ikkitasi parallel ketsa
    baza ustida keraksiz raqobat bo'lardi. Navbatda bir nechtasi tursa,
    keyingi tik keyingisini oladi."""
    reclaimed = await _reclaim_stale(db)

    period_row = await db.scalar(
        select(PayrollPeriod)
        .where(PayrollPeriod.calc_state == "queued")
        .order_by(PayrollPeriod.calc_requested_at)
        .limit(1)
    )
    if period_row is None:
        return {"ran": None, "reclaimed": reclaimed}

    period = period_row.period
    user_ids = list(period_row.calc_user_ids) if period_row.calc_user_ids else None
    actor_id = period_row.calc_requested_by

    period_row.calc_state = "running"
    period_row.calc_started_at = datetime.utcnow()
    period_row.calc_progress = 0
    period_row.calc_error = None
    await db.commit()

    async def on_progress(done: int, total: int) -> None:
        # ATAYLAB O'SHA sessiyada: alohida ulanishdan UPDATE qilinsa SQLite'da
        # `run_payroll` ushlab turgan yozuv qulfiga urilib, o'zaro kutish
        # (deadlock) yuzaga kelardi. Bu nuqtada joriy xodimning payslip'i va
        # uning barcha qatorlari to'liq yozilgan — ya'ni commit xavfsiz.
        await db.execute(
            update(PayrollPeriod)
            .where(PayrollPeriod.period == period)
            .values(calc_progress=done, calc_total=total)
        )
        await db.commit()

    try:
        # Import funksiya ichida: `payroll.py` ↔ `payroll_jobs.py` aylanma
        # importini oldini oladi va cron har daqiqada ishga tushganda
        # (ish yo'q bo'lsa ham) og'ir modulni ko'tarmaydi.
        from api.services.payroll import run_payroll

        result = await run_payroll(db, period, user_ids=user_ids, on_progress=on_progress)
    except Exception as exc:  # noqa: BLE001 — cron jim o'lmasin
        await db.rollback()
        row = await db.scalar(select(PayrollPeriod).where(PayrollPeriod.period == period))
        if row is not None:
            row.calc_state = "error"
            row.calc_error = f"{type(exc).__name__}: {exc}"[:500]
            await db.commit()
        return {"ran": period, "ok": False, "error": f"{type(exc).__name__}: {exc}", "reclaimed": reclaimed}

    # ── Xabar va audit — endi SO'ROVDAN TASHQARIDA ──
    # Ilgari bular `calculate` endpointi ichida edi: har rahbarga FCM + Telegram
    # (timeout 10s), ya'ni saytni qotirgan vaqtning kattaroq qismi aynan shu edi.
    rows = list(await db.scalars(select(Payslip).where(Payslip.period == period)))
    total_net = sum(float(p.net) for p in rows)
    managers = list(
        await db.scalars(
            select(User).where(
                User.role.in_((Role.hr.value, Role.boss.value)), User.telegram_id.isnot(None)
            )
        )
    )
    from api.notify import notify_user
    from api.services.push import Category

    for m in managers:
        await notify_user(
            db,
            m,
            Category.APPROVALS,
            f"💰 Payroll tayyor ({period}): {result['calculated']} xodim, jami ~{total_net:,.0f} so'm. "
            f"Tasdiqlash uchun saytga kiring.".replace(",", " "),
            data={"path": "/payroll"},
        )

    db.add(
        AuditLog(
            actor_id=actor_id,
            action="payroll_calculated",
            target_user_id=None,
            before=None,
            after={"period": period, "calculated": result["calculated"], "total_net": total_net},
        )
    )

    row = await db.scalar(select(PayrollPeriod).where(PayrollPeriod.period == period))
    if row is not None:
        row.calc_state = "done"
        row.calc_progress = result["calculated"]
        row.calc_total = result["calculated"]
        row.calc_error = None
    await db.commit()

    return {
        "ran": period,
        "ok": True,
        "calculated": result["calculated"],
        "total_net": total_net,
        "reclaimed": reclaimed,
    }
