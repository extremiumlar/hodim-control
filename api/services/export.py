from datetime import date, datetime
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Font
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Bonus, DailyResult, ExcusedDay, ExcusedStatus, Role, TaskModel, TaskStatus, User

HEADERS = [
    "Xodim",
    "Suhbatlar (jami)",
    "Tashriflar (jami)",
    "Vazifalar (bajarilgan/jami)",
    "Sababli kunlar (tasdiqlangan)",
    "Bonus (agar bitta oy tanlangan bo'lsa)",
]


async def build_report_xlsx(db: AsyncSession, date_from: date, date_to: date) -> BytesIO:
    day_start = datetime.combine(date_from, datetime.min.time())
    day_end = datetime.combine(date_to, datetime.max.time())

    # Bonus faqat aniq bitta oy tanlanganda ko'rsatiladi (davr YYYY-MM formatida saqlanadi,
    # ixtiyoriy sana oralig'i uchun bir nechta oyni yig'ish MVP doirasidan tashqarida).
    single_month_period = (
        date_from.strftime("%Y-%m") if date_from.strftime("%Y-%m") == date_to.strftime("%Y-%m") else None
    )

    employees = list(
        await db.scalars(
            select(User).where(User.role == Role.employee.value, User.is_active == True).order_by(User.full_name)  # noqa: E712
        )
    )

    wb = Workbook()
    ws = wb.active
    ws.title = "Hisobot"
    ws.append([f"Hisobot davri: {date_from.isoformat()} — {date_to.isoformat()}"])
    ws.append(HEADERS)
    for cell in ws[2]:
        cell.font = Font(bold=True)

    for emp in employees:
        results = list(
            await db.scalars(
                select(DailyResult).where(
                    DailyResult.user_id == emp.id, DailyResult.date >= date_from, DailyResult.date <= date_to
                )
            )
        )
        total_conversations = sum(r.conversations_count for r in results)
        total_visits = sum(r.visits_count for r in results)

        tasks = list(
            await db.scalars(
                select(TaskModel).where(
                    TaskModel.assigned_to == emp.id,
                    TaskModel.created_at >= day_start,
                    TaskModel.created_at <= day_end,
                )
            )
        )
        tasks_total = len(tasks)
        tasks_done = sum(1 for t in tasks if t.status == TaskStatus.done.value)

        excused_count = len(
            list(
                await db.scalars(
                    select(ExcusedDay).where(
                        ExcusedDay.user_id == emp.id,
                        ExcusedDay.date >= date_from,
                        ExcusedDay.date <= date_to,
                        ExcusedDay.status == ExcusedStatus.approved.value,
                    )
                )
            )
        )

        bonus_amount = ""
        if single_month_period:
            bonus = await db.scalar(
                select(Bonus).where(Bonus.user_id == emp.id, Bonus.period == single_month_period)
            )
            if bonus:
                bonus_amount = float(bonus.amount)

        ws.append(
            [
                emp.full_name,
                total_conversations,
                total_visits,
                f"{tasks_done}/{tasks_total}",
                excused_count,
                bonus_amount,
            ]
        )

    for column_cells in ws.columns:
        length = max(len(str(cell.value)) for cell in column_cells if cell.value is not None) if any(
            cell.value is not None for cell in column_cells
        ) else 10
        ws.column_dimensions[column_cells[0].column_letter].width = min(max(length + 2, 12), 40)

    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer
