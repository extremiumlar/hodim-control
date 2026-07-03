from datetime import date, datetime

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import settings
from api.deps import get_db, require_roles, verify_bot_secret
from api.services.export import build_report_xlsx
from api.timeutil import today_local
from api.telegram_notify import send_message
from crm import get_crm_adapter
from db.models import ExcusedDay, ExcusedStatus, Role, TaskModel, TaskStatus, User

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/export")
async def export_report(
    date_from: date,
    date_to: date,
    _: User = Depends(require_roles(Role.hr.value, Role.rop.value, Role.boss.value)),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    buffer = await build_report_xlsx(db, date_from, date_to)
    filename = f"hisobot_{date_from.isoformat()}_{date_to.isoformat()}.xlsx"
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/daily-summary", dependencies=[Depends(verify_bot_secret)])
async def daily_summary(db: AsyncSession = Depends(get_db)) -> dict:
    """Scheduler tomonidan har kuni (~19:00) chaqiriladi — umumiy guruhga
    kunlik xulosani monospace formatda yuboradi."""
    today = today_local()
    day_start = datetime.combine(today, datetime.min.time())
    day_end = datetime.combine(today, datetime.max.time())

    employees = list(
        await db.scalars(
            select(User).where(User.role == Role.employee.value, User.is_active == True).order_by(User.full_name)  # noqa: E712
        )
    )

    lines = []
    for emp in employees:
        excused = await db.scalar(
            select(ExcusedDay).where(
                ExcusedDay.user_id == emp.id,
                ExcusedDay.date == today,
                ExcusedDay.status == ExcusedStatus.approved.value,
            )
        )
        if excused:
            lines.append(f"{'🙋 ' + emp.full_name:<28} sababli kun")
            continue

        tasks_today = list(
            await db.scalars(
                select(TaskModel).where(
                    TaskModel.assigned_to == emp.id,
                    TaskModel.created_at >= day_start,
                    TaskModel.created_at <= day_end,
                )
            )
        )
        total = len(tasks_today)
        done = sum(1 for t in tasks_today if t.status == TaskStatus.done.value)
        mark = "✅" if total > 0 and done == total else ("❌" if total > 0 else "•")
        lines.append(f"{mark + ' ' + emp.full_name:<28} {done}/{total} vazifa")

    body = "\n".join(lines) if lines else "Xodimlar topilmadi."
    # API xabarlarni HTML parse_mode bilan yuboradi (api/telegram_notify.py), shuning uchun
    # Telegram monospace bloki uchun ```  emas balki <pre> tegi ishlatiladi.
    text = f"📊 Kunlik xulosa — {today.isoformat()}\n<pre>{body}</pre>"

    sent = False
    if settings.telegram_group_chat_id:
        result = await send_message(settings.telegram_group_chat_id, text)
        sent = result is not None

    return {"employees": len(employees), "sent": sent}


@router.post("/call-stats", dependencies=[Depends(verify_bot_secret)])
async def call_stats(db: AsyncSession = Depends(get_db)) -> dict:
    """Bot `/statistika` buyrug'i orqali talab bo'yicha chaqiradi — CRM'dan (hozircha Uysot)
    shu kunda har bir operator/managerning nechta qo'ng'iroq qilgani/qabul qilganini olib,
    guruhga jo'natadi."""
    adapter = get_crm_adapter(settings.crm_type)
    if not adapter:
        return {"sent": False, "reason": "CRM sozlanmagan"}

    today = today_local()
    counts = await adapter.get_all_daily_call_counts(today)
    if not counts:
        return {"sent": False, "reason": "Bugun uchun qo'ng'iroq ma'lumoti topilmadi"}

    users = list(await db.scalars(select(User).where(User.crm_external_id.isnot(None))))
    name_by_external_id = {u.crm_external_id: u.full_name for u in users}

    rows = sorted(counts.items(), key=lambda item: item[1], reverse=True)
    lines = [
        f"{name_by_external_id.get(external_id, external_id):<28} {count} qo'ng'iroq"
        for external_id, count in rows
    ]
    text = f"📞 Bugungi qo'ng'iroqlar — {today.isoformat()}\n<pre>{chr(10).join(lines)}</pre>"

    sent = False
    if settings.telegram_group_chat_id:
        result = await send_message(settings.telegram_group_chat_id, text)
        sent = result is not None

    return {"operators": len(counts), "sent": sent}
