from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_db, require_roles, verify_bot_secret
from api.services.daily_digest import send_daily_digest
from api.services.export import build_report_xlsx
from api.services.weekly_digest import send_weekly_digest
from api.timeutil import today_local
from db.models import Role, User

router = APIRouter(prefix="/reports", tags=["reports"])


class SummaryTarget(BaseModel):
    """Ixtiyoriy nishon chat: berilmasa — sozlangan umumiy guruhga yuboriladi.
    Bot HR/ROP/Boshliq/Dasturchi shaxsiy chatda so'raganida o'sha chatga yuborish
    uchun ishlatiladi."""

    chat_id: int | None = None


@router.get("/export")
async def export_report(
    date_from: date,
    date_to: date,
    _: User = Depends(require_roles(Role.hr.value, Role.rop.value, Role.boss.value, Role.dasturchi.value)),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    buffer = await build_report_xlsx(db, date_from, date_to)
    filename = f"hisobot_{date_from.isoformat()}_{date_to.isoformat()}.xlsx"
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


BOT_EXPORT_PERIODS = {"today", "week", "month"}


@router.get("/export-bot/{telegram_id}", dependencies=[Depends(verify_bot_secret)])
async def export_report_for_bot(
    telegram_id: int, period: str = "month", db: AsyncSession = Depends(get_db)
) -> StreamingResponse:
    """Bot "📥 Hisobot (Excel)" tugmasi uchun: davr (bugun / shu hafta / shu oy)
    Toshkent sanasi bo'yicha backendda hisoblanadi — bot server vaqtiga bog'liq emas."""
    actor = await db.scalar(select(User).where(User.telegram_id == telegram_id))
    if not actor or actor.role not in {Role.hr.value, Role.rop.value, Role.boss.value, Role.dasturchi.value}:
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
