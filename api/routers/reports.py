from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy.orm import selectinload

from api.deps import get_db, require_roles, verify_bot_secret
from api.routers.payroll import can_view_payroll
from api.services.daily_digest import send_daily_digest
from api.services.background_jobs import enqueue
from api.services.export import build_report_xlsx
from api.services.weekly_digest import send_weekly_digest
from api.timeutil import today_local
from db.models import BackgroundJob, Role, User

router = APIRouter(prefix="/reports", tags=["reports"])


async def _visible_user_ids(db: AsyncSession, actor: User) -> list[int] | None:
    """Chaqiruvchi hisobotda ko'ra oladigan xodimlar. `None` — cheklovsiz.

    `can_view_payroll` lavozimga ham qaraydi (`managed_by_roles`), shuning
    uchun `selectinload(User.position)` bilan yuklanadi — aks holda lazy-load
    async sessiyada xato beradi."""
    if actor.role != Role.rop.value:
        return None
    users = await db.scalars(select(User).options(selectinload(User.position)))
    return [u.id for u in users if can_view_payroll(actor, u)]


class SummaryTarget(BaseModel):
    """Ixtiyoriy nishon chat: berilmasa — sozlangan umumiy guruhga yuboriladi.
    Bot HR/ROP/Boshliq/Dasturchi shaxsiy chatda so'raganida o'sha chatga yuborish
    uchun ishlatiladi."""

    chat_id: int | None = None


@router.get("/export")
async def export_report(
    date_from: date,
    date_to: date,
    actor: User = Depends(require_roles(Role.hr.value, Role.rop.value, Role.boss.value, Role.dasturchi.value)),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    # XAVFSIZLIK: XLSX ichida har bir xodimning BONUS summasi bor, chaqiruvchi
    # esa ilgari umuman hisobga olinmasdi — ROP butun tashkilotning bonuslarini
    # yuklab olardi. Qamrov `can_view_payroll` bilan bir xil.
    buffer = await build_report_xlsx(db, date_from, date_to, await _visible_user_ids(db, actor))
    filename = f"hisobot_{date_from.isoformat()}_{date_to.isoformat()}.xlsx"
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


BOT_EXPORT_PERIODS = {"today", "week", "month"}


@router.post("/export-async", status_code=status.HTTP_202_ACCEPTED)
async def export_report_async(
    date_from: date,
    date_to: date,
    actor: User = Depends(require_roles(Role.hr.value, Role.rop.value, Role.boss.value, Role.dasturchi.value)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Hisobotni NAVBATGA qo'yadi va darhol qaytadi (TZ 2.2 / S-07).

    NEGA: `GET /export` faylni SO'ROV ICHIDA yasaydi. cPanel'da
    konkurentlik = 1, ya'ni o'sha vaqt davomida butun sayt javob bermaydi.
    Endi og'ir ish cron jarayonida bajariladi, tayyor fayl esa botga
    yuboriladi.

    Qamrov so'rov paytida hisoblanadi va ishga YOZIB qo'yiladi — aks holda
    cron bajarayotgan paytda huquq o'zgarsa natija noto'g'ri chiqardi."""
    if not actor.telegram_id:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Fayl Telegram orqali yuboriladi — avval botga /start bosing.",
        )
    job = await enqueue(
        db,
        "report_export",
        {
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "user_ids": await _visible_user_ids(db, actor),
        },
        actor.id,
    )
    await db.commit()
    return {"job_id": job.id, "status": job.status,
            "message": "Hisobot tayyorlanmoqda — tayyor bo'lgach botga yuboriladi."}


@router.get("/jobs/{job_id}")
async def job_status(
    job_id: int,
    actor: User = Depends(require_roles(Role.hr.value, Role.rop.value, Role.boss.value, Role.dasturchi.value)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Fon ishining holati. Begona ishga 404 (S-06 qoidasi)."""
    job = await db.get(BackgroundJob, job_id)
    if job is None or job.user_id != actor.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Topilmadi")
    return {
        "job_id": job.id,
        "kind": job.kind,
        "status": job.status,
        "note": job.result_note,
        "error": job.error,
    }


@router.get("/export-bot/{telegram_id}", dependencies=[Depends(verify_bot_secret)])
async def export_report_for_bot(
    telegram_id: int, period: str = "month", db: AsyncSession = Depends(get_db)
) -> StreamingResponse:
    """Bot "📥 Hisobot (Excel)" tugmasi uchun: davr (bugun / shu hafta / shu oy)
    Toshkent sanasi bo'yicha backendda hisoblanadi — bot server vaqtiga bog'liq emas."""
    actor = await db.scalar(select(User).where(User.telegram_id == telegram_id))
    if not actor or not actor.is_active or actor.role not in {Role.hr.value, Role.rop.value, Role.boss.value, Role.dasturchi.value}:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Bu amal uchun ruxsat yo'q")
    if period not in BOT_EXPORT_PERIODS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Noma'lum davr")

    today = today_local()
    if period == "today":
        date_from = today
    elif period == "week":
        date_from = today - timedelta(days=today.weekday())
    else:
        date_from = today.replace(day=1)

    buffer = await build_report_xlsx(db, date_from, today)
    filename = f"hisobot_{date_from.isoformat()}_{today.isoformat()}.xlsx"
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/daily-digest", dependencies=[Depends(verify_bot_secret)])
async def daily_digest(
    payload: SummaryTarget | None = None, dry_run: bool = False, db: AsyncSession = Depends(get_db)
) -> dict:
    """Kunlik yagona digest — vazifalar, qo'ng'iroq/lid/tashrif (kechaga nisbatan)
    va AI xulosa BITTA xabarda. Guruhga avtomatik yuborishni `/stats/lead-stages/group-tick`
    qiladi (boss belgilagan vaqtda); bu endpoint bot talab bo'yicha chaqirganda ishlatiladi
    (`chat_id` — shaxsiy chatga)."""
    return await send_daily_digest(db, chat_id=payload.chat_id if payload else None, dry_run=dry_run)


@router.post("/weekly-digest", dependencies=[Depends(verify_bot_secret)])
async def weekly_digest(
    payload: SummaryTarget | None = None, dry_run: bool = False, db: AsyncSession = Depends(get_db)
) -> dict:
    """Haftalik raqamli yakun (shu hafta vs o'tgan hafta, operator kesimida) — sof kod
    hisobi, AI o'chiq bo'lsa ham ishlaydi. Scheduler yakshanba kechqurun chaqiradi;
    AI'ning shaxsiy haftalik trend xabarlari (/ai-watch/weekly-run) bunga qo'shimcha."""
    return await send_weekly_digest(db, chat_id=payload.chat_id if payload else None, dry_run=dry_run)


@router.post("/monthly-digest", dependencies=[Depends(verify_bot_secret)])
async def monthly_digest(
    payload: SummaryTarget | None = None, dry_run: bool = False, db: AsyncSession = Depends(get_db)
) -> dict:
    """Oylik yakun (joriy oy vs o'tgan kalendar oy, operator kesimida, bonus bilan) —
    sof kod hisobi. Scheduler oyning oxirgi kuni kechqurun chaqiradi; bot /oylik
    buyrug'i bilan istalgan payt so'ralishi mumkin (chat_id — o'sha chatga)."""
    from api.services.monthly_digest import send_monthly_digest

    return await send_monthly_digest(db, chat_id=payload.chat_id if payload else None, dry_run=dry_run)


@router.post("/yesterday-correction", dependencies=[Depends(verify_bot_secret)])
async def yesterday_correction(dry_run: bool = False, db: AsyncSession = Depends(get_db)) -> dict:
    """Ertalabki "kecha yakuni" tuzatishi: kechagi yakuniy (23:57 muzlatilgan)
    raqamlar kechqurungi digestda ko'rsatilganidan sezilarli oshgan bo'lsagina
    guruh(lar)ga qisqa xabar. Scheduler har kuni ertalab chaqiradi."""
    from api.services.daily_digest import send_yesterday_correction

    return await send_yesterday_correction(db, dry_run=dry_run)
