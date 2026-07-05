from datetime import date
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Font
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.routers.norms import METRIC_LABELS, metrics_for
from api.routers.stats import _confirmed_videos_count
from api.timeutil import local_range_utc_naive
from db.models import Bonus, DailyResult, ExcusedDay, ExcusedStatus, Role, TaskModel, TaskStatus, User

# Ustunlar tartibi barqaror bo'lishi uchun (faqat faol xodimlar lavozimlarida
# uchraydigan metrikalar ko'rsatiladi, lekin tartib doim shu).
METRIC_ORDER = list(METRIC_LABELS)
METRIC_TOTAL_LABELS = {"suhbat": "Suhbatlar (jami)", "tashrif": "Tashriflar (jami)", "video": "Videolar (jami)"}

FIXED_HEADERS = [
    "Vazifalar (bajarilgan/jami)",
    "Sababli kunlar (tasdiqlangan)",
    "Bonus (agar bitta oy tanlangan bo'lsa)",
]


async def build_report_xlsx(db: AsyncSession, date_from: date, date_to: date) -> BytesIO:
    day_start, day_end = local_range_utc_naive(date_from, date_to)

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

    # Ustunlar dinamik: kamida bitta faol xodim lavozimida uchraydigan metrikalar.
    # Xodimda kuzatilmaydigan metrika 0 emas "—" bilan ko'rsatiladi — "0 natija"
    # va "umuman kuzatilmaydi" farqi yo'qolmasligi uchun.
    metrics_by_user = {emp.id: metrics_for(emp) for emp in employees}
    used_metrics = [m for m in METRIC_ORDER if any(m in keys for keys in metrics_by_user.values())]

    wb = Workbook()
    ws = wb.active
    ws.title = "Hisobot"
    ws.append([f"Hisobot davri: {date_from.isoformat()} — {date_to.isoformat()}"])
    ws.append(["Xodim", *(METRIC_TOTAL_LABELS[m] for m in used_metrics), *FIXED_HEADERS])
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
        totals = {
            "suhbat": sum(r.conversations_count for r in results),
            "tashrif": sum(r.visits_count for r in results),
        }
        if "video" in metrics_by_user[emp.id]:
            totals["video"] = await _confirmed_videos_count(db, emp.id, date_from, date_to)

        metric_cells = [
            totals.get(m, 0) if m in metrics_by_user[emp.id] else "—" for m in used_metrics
        ]

        tasks = list(
            await db.scalars(
                select(TaskModel).where(
                    TaskModel.assigned_to == emp.id,
                    TaskModel.created_at >= day_start,
                    TaskModel.created_at < day_end,
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
                *metric_cells,
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
