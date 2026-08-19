"""Og'ir ishlar navbati — UMUMIY mexanizm (yangi TZ 2.2 / S-07).

MUAMMO
──────
cPanel Passenger'da konkurentlik = **1**. Ya'ni bitta uzoq so'rov butun
saytni (va API'ni) navbatga qo'yadi. Excel eksporti aynan shunday edi:
`build_report_xlsx` so'rov ichida ishlaydi, o'sha paytda hech kim sahifa
ocholmaydi.

YECHIM
──────
So'rov ishni NAVBATGA qo'yadi va darhol `202 {"job_id": N}` qaytaradi.
Og'ir ishni `scripts/cron_tick.py` alohida JARAYONDA bajaradi va natijani
foydalanuvchiga Telegram orqali yuboradi.

Oylik hisobi uchun allaqachon shunga o'xshash navbat bor
(`payroll_jobs.py`), lekin u O'SHA modulga xos: progress ustunlari, davr
qulfi, bonus qayta hisobi. Bu esa umumiy — yangi og'ir ish qo'shish uchun
bitta ishlovchi funksiya yozib, `_HANDLERS` ga qo'shish kifoya.

⚠️ HOLAT FAQAT BAZADA. Cron har daqiqada YANGI jarayon ko'taradi — modul
darajasidagi navbat yoki lock ishlamaydi (TZ tuzog'i).

⚠️ NATIJA SERVERDA SAQLANMAYDI. Fayl Telegram'ga yuklanadi va faqat
`file_id` yoziladi: disk kvotasi tor (1 GB) va TZ 1.1 shuni talab qiladi.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import BackgroundJob, BackgroundJobStatus, User

# `running` holatida shuncha daqiqadan ko'p turgan ish — o'lgan jarayon
# qoldig'i (cron o'ldirilgan, server qayta yuklangan). Aks holda navbat
# abadiy tiqilib qolardi.
STALE_RUNNING_MINUTES = 20

# Bitta natija fayli nomi + baytlari.
JobResult = tuple[str, bytes, str]  # (fayl nomi, baytlar, foydalanuvchiga izoh)

_HANDLERS: dict[str, Callable[[AsyncSession, dict, User | None], Awaitable[JobResult]]] = {}


def handler(kind: str):
    """Ishlovchini ro'yxatdan o'tkazadi: `@handler("report_export")`."""

    def wrap(fn):
        _HANDLERS[kind] = fn
        return fn

    return wrap


async def enqueue(
    db: AsyncSession, kind: str, params: dict, user_id: int | None
) -> BackgroundJob:
    """Ishni navbatga qo'yadi. Chaqiruvchi COMMIT qiladi."""
    if kind not in _HANDLERS:
        raise ValueError(f"noma'lum ish turi: {kind}")
    job = BackgroundJob(
        kind=kind, params=params, user_id=user_id, status=BackgroundJobStatus.queued.value
    )
    db.add(job)
    await db.flush()
    return job


async def _reclaim_stale(db: AsyncSession) -> int:
    chegara = datetime.utcnow() - timedelta(minutes=STALE_RUNNING_MINUTES)
    rows = list(
        await db.scalars(
            select(BackgroundJob).where(
                BackgroundJob.status == BackgroundJobStatus.running.value,
                BackgroundJob.started_at.isnot(None),
                BackgroundJob.started_at < chegara,
            )
        )
    )
    for row in rows:
        row.status = BackgroundJobStatus.failed.value
        row.error = f"{STALE_RUNNING_MINUTES} daqiqadan oshdi — jarayon uzilgan bo'lishi mumkin"
        row.finished_at = datetime.utcnow()
    if rows:
        await db.commit()
    return len(rows)


async def background_tick(db: AsyncSession) -> dict:
    """Navbatdagi BITTA ishni bajaradi. Cron har daqiqada chaqiradi.

    Bir vaqtda bitta: ishlar og'ir, ikkitasi parallel ketsa yagona ishchiga
    emas, balki bazaga bosim tushardi. Navbatda bir nechtasi tursa keyingi
    tik keyingisini oladi."""
    reclaimed = await _reclaim_stale(db)

    job = await db.scalar(
        select(BackgroundJob)
        .where(BackgroundJob.status == BackgroundJobStatus.queued.value)
        .order_by(BackgroundJob.created_at)
        .limit(1)
    )
    if job is None:
        return {"ran": None, "reclaimed": reclaimed}

    job.status = BackgroundJobStatus.running.value
    job.started_at = datetime.utcnow()
    job.error = None
    # DARHOL commit: shu qatorning o'zi «band» belgisi. Aks holda keyingi
    # tik (yoki ikkinchi jarayon) o'sha ishni qaytadan olardi.
    await db.commit()

    kind, job_id, params = job.kind, job.id, (job.params or {})
    user = await db.get(User, job.user_id) if job.user_id else None
    # ⚠️ `telegram_id` ni HOZIR o'qib olamiz. Xato yuz berganda `rollback()`
    # sessiyadagi BARCHA obyektni bekor qiladi (bu `expire_on_commit=False`
    # ga BOG'LIQ EMAS) va keyin `user.telegram_id` ga murojaat qilish
    # async kontekstda `MissingGreenlet` bilan yiqiladi — ya'ni xato
    # ishlovchisining O'ZI xato berardi.
    tg_id = user.telegram_id if user is not None else None

    try:
        fn = _HANDLERS.get(kind)
        if fn is None:
            raise ValueError(f"ishlovchi topilmadi: {kind}")
        filename, content, note = await fn(db, params, user)
    except Exception as exc:  # noqa: BLE001 — cron jim o'lmasin
        await db.rollback()
        row = await db.get(BackgroundJob, job_id)
        if row is not None:
            row.status = BackgroundJobStatus.failed.value
            row.error = f"{type(exc).__name__}: {exc}"[:500]
            row.finished_at = datetime.utcnow()
            await db.commit()
        if tg_id:
            from api.telegram_notify import send_message

            await send_message(
                tg_id,
                f"⚠️ «{kind}» tayyorlanmadi: {type(exc).__name__}. Qayta urinib ko'ring.",
            )
        return {"ran": kind, "job_id": job_id, "ok": False, "error": str(exc)[:200],
                "reclaimed": reclaimed}

    # ── Natijani yetkazish ──
    file_id = None
    yetkazildi = False
    if tg_id:
        from api.telegram_notify import extract_file_id, send_media_file

        resp = await send_media_file(tg_id, content, filename, "document", caption=note)
        file_id = extract_file_id(resp)
        yetkazildi = resp is not None

    row = await db.get(BackgroundJob, job_id)
    if row is not None:
        row.status = BackgroundJobStatus.done.value
        row.result_file_id = file_id
        row.result_note = (
            note if yetkazildi else "Tayyor, lekin Telegram orqali yuborilmadi"
        )[:300]
        row.finished_at = datetime.utcnow()
        await db.commit()

    return {
        "ran": kind,
        "job_id": job_id,
        "ok": True,
        "delivered": yetkazildi,
        "bytes": len(content),
        "reclaimed": reclaimed,
    }


# ─────────────────────────────────────────────────────────────
# ISHLOVCHILAR
# ─────────────────────────────────────────────────────────────


@handler("report_export")
async def _report_export(db: AsyncSession, params: dict, user: User | None) -> JobResult:
    """Umumiy hisobot (Excel) — `GET /reports/export` ning fon varianti."""
    from datetime import date as _date

    from api.services.export import build_report_xlsx

    date_from = _date.fromisoformat(params["date_from"])
    date_to = _date.fromisoformat(params["date_to"])
    user_ids = params.get("user_ids")
    buffer = await build_report_xlsx(db, date_from, date_to, user_ids)
    nom = f"hisobot_{date_from.isoformat()}_{date_to.isoformat()}.xlsx"
    return nom, buffer.read(), f"📊 Hisobot tayyor: {date_from} — {date_to}"


@handler("payroll_export")
async def _payroll_export(db: AsyncSession, params: dict, user: User | None) -> JobResult:
    """Oylik varaqasi (Excel) — `GET /payroll/{period}/export` fon varianti."""
    from api.services.export import build_payroll_xlsx

    period = params["period"]
    buffer = await build_payroll_xlsx(db, period, user_ids=params.get("user_ids"))
    return f"oylik_{period}.xlsx", buffer.read(), f"💵 Oylik varaqasi tayyor: {period}"
