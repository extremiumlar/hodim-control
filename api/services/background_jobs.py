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

import logging

from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import BackgroundJob, BackgroundJobStatus, User

logger = logging.getLogger(__name__)

# `running` holatida shuncha daqiqadan ko'p turgan ish — o'lgan jarayon
# qoldig'i (cron o'ldirilgan, server qayta yuklangan). Aks holda navbat
# abadiy tiqilib qolardi.
STALE_RUNNING_MINUTES = 20

# Bitta natija fayli nomi + baytlari.
JobResult = tuple[str, bytes, str]  # (fayl nomi, baytlar, foydalanuvchiga izoh)

_HANDLERS: dict[str, Callable[[AsyncSession, dict, User | None], Awaitable[JobResult]]] = {}

#  Fayl Telegram'ga YETKAZILGANDAN KEYIN chaqiriladigan ilgak.
#  NEGA KERAK: ba'zi ishlar natijaning `file_id` sini bilishi shart
#  (masalan ma'lumotnoma kadr arxiviga yozilishi kerak), lekin yuborish
#  `background_tick` ning ichida bo'ladi — ishlovchining o'zi `file_id`
#  ni ko'ra olmaydi.
_AFTER: dict[str, Callable[[AsyncSession, dict, str | None], Awaitable[None]]] = {}


def handler(kind: str):
    """Ishlovchini ro'yxatdan o'tkazadi: `@handler("report_export")`."""

    def wrap(fn):
        _HANDLERS[kind] = fn
        return fn

    return wrap


def after_delivery(kind: str):
    """Yetkazilgandan keyingi ilgak: `@after_delivery("document_render")`.

    Ilgakdagi xato ISHNI YIQITMAYDI — fayl allaqachon foydalanuvchida.
    Xato faqat jurnalga yoziladi."""

    def wrap(fn):
        _AFTER[kind] = fn
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

    keyin = _AFTER.get(kind)
    if keyin is not None:
        try:
            await keyin(db, params, file_id)
        except Exception:  # noqa: BLE001
            #  Ish MUVAFFAQIYATLI hisoblanadi: fayl foydalanuvchida.
            #  Ilgak (masalan arxivga yozish) alohida muammo.
            logger.exception("«%s» ishining keyingi ilgagi xato berdi", kind)
            await db.rollback()

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


@handler("document_render")
async def _document_render(db: AsyncSession, params: dict, user: User | None) -> JobResult:
    """Shablondan `.docx` tayyorlash (yangi TZ 3.3 / S-14).

    NEGA FON ISHI: shablon Telegram'dan yuklab olinadi (tarmoq), keyin
    ZIP ochilib qayta yig'iladi. Passenger'da konkurentlik = 1, ya'ni bu
    so'rov ichida bajarilsa butun sayt kutib turardi.

    Natija Telegram orqali SO'RAGAN odamga boradi va serverda
    saqlanmaydi — `file_id` yoziladi (TZ 1.1)."""
    from api.services.docx_render import render
    from api.telegram_notify import download_file
    from db.models import DocumentTemplate

    tmpl = await db.get(DocumentTemplate, int(params["template_id"]))
    if tmpl is None or not tmpl.is_active:
        raise ValueError("Shablon topilmadi yoki o'chirilgan")

    xom = await download_file(tmpl.file_id)
    if xom is None:
        #  Bot tokeni yo'q (lokal sinov) yoki Telegram fayli eskirgan.
        #  Aniq xabar: HR «nega ishlamadi?» deb qidirmasin.
        raise ValueError(
            "Shablon faylini Telegram'dan olib bo'lmadi — uni qayta yuklang"
        )

    natija, qolgan = render(xom, {k: str(v) for k, v in (params.get("values") or {}).items()})
    nom = params.get("filename") or f"{tmpl.name}.docx"
    if not nom.endswith(".docx"):
        nom += ".docx"

    izoh = f"📄 <b>{tmpl.name}</b> tayyor"
    if qolgan:
        #  To'ldirilmagan belgi hujjatda `{{...}}` bo'lib qoladi — HR buni
        #  BILISHI shart, aks holda shundayligicha jo'natib yuborardi.
        izoh += "\n⚠️ To'ldirilmagan: " + ", ".join(qolgan)
    return nom, natija, izoh


@after_delivery("document_render")
async def _document_to_archive(db: AsyncSession, params: dict, file_id: str | None) -> None:
    """Tayyor ma'lumotnomani KADR ARXIVIGA yozadi (yangi TZ 3.9 / S-17).

    Faqat `certificate_id` bo'lgan ishlarda ishlaydi — oddiy hujjat
    generatsiyasi (ish taklifi va h.k.) arxivga tushmaydi, u nomzodniki
    va xodim hujjati emas.

    `file_id` bo'lmasa (yuborilmadi) yozilmaydi: arxivda ochib
    bo'lmaydigan yozuv turgani yo'qidan yomonroq — HR uni bor deb
    o'ylab, keyin topa olmaydi."""
    from datetime import date as _date

    from db.models import Certificate, DocumentType, EmployeeDocument

    cert_id = params.get("certificate_id")
    if not cert_id or not file_id:
        return

    cert = await db.get(Certificate, int(cert_id))
    if cert is None or cert.document_id:
        return

    doc = EmployeeDocument(
        user_id=cert.user_id,
        doc_type=DocumentType.other.value,
        name=f"Ma'lumotnoma {cert.number}",
        file_id=file_id,
        file_type="document",
        uploaded_by=cert.issued_by,
        issued_at=cert.issued_at or _date.today(),
        note=f"Maqsad: {cert.purpose}",
    )
    db.add(doc)
    await db.flush()
    cert.document_id = doc.id
    await db.commit()
