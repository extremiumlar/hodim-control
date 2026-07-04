from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_db, verify_bot_secret
from api.routers.norms import METRIC_LABELS, metrics_for
from api.schemas import MetricProgressRow, MyStatsOut
from api.timeutil import local_range_utc_naive, today_local
from db.models import (
    DailyResult,
    ExcusedDay,
    ExcusedStatus,
    MobilografStatus,
    MobilografVideo,
    Norm,
    TaskModel,
    TaskStatus,
    User,
)

router = APIRouter(prefix="/stats", tags=["stats"])


async def _current_norm(db: AsyncSession, user_id: int, metric_type: str) -> int | None:
    norm = await db.scalar(
        select(Norm)
        .where(Norm.user_id == user_id, Norm.metric_type == metric_type)
        .order_by(Norm.effective_from.desc(), Norm.created_at.desc())
        .limit(1)
    )
    return norm.value if norm else None


async def _confirmed_videos_count(db: AsyncSession, user_id: int, day_from: date, day_to: date) -> int:
    """[day_from, day_to] mahalliy kunlar oralig'ida tasdiqlangan mobilograf
    videolar soni (sent_at bazada naive-UTC saqlanadi)."""
    start_utc, end_utc = local_range_utc_naive(day_from, day_to)
    return (
        await db.scalar(
            select(func.count(MobilografVideo.id)).where(
                MobilografVideo.user_id == user_id,
                MobilografVideo.status == MobilografStatus.confirmed.value,
                MobilografVideo.sent_at >= start_utc,
                MobilografVideo.sent_at < end_utc,
            )
        )
    ) or 0


async def today_metric_rows(db: AsyncSession, user: User) -> list[MetricProgressRow]:
    """Xodimning bugungi ko'rsatkichlari (lavozimiga qarab) — qiymat va norma.
    Bot menyusidagi "Bugungi normam" va "Statistikam" uchun umumiy qism."""
    today = today_local()
    result = await db.scalar(
        select(DailyResult).where(DailyResult.user_id == user.id, DailyResult.date == today)
    )

    values = {
        "suhbat": result.conversations_count if result else 0,
        "tashrif": result.visits_count if result else 0,
    }

    rows = []
    for key in metrics_for(user):
        if key == "video":
            value = await _confirmed_videos_count(db, user.id, today, today)
        else:
            value = values.get(key, 0)
        rows.append(
            MetricProgressRow(
                key=key,
                label=METRIC_LABELS.get(key, key),
                value=value,
                norm=await _current_norm(db, user.id, key),
            )
        )
    return rows


@router.get("/my/{telegram_id}", response_model=MyStatsOut, dependencies=[Depends(verify_bot_secret)])
async def my_stats(telegram_id: int, db: AsyncSession = Depends(get_db)) -> MyStatsOut:
    """Har bir xodim botdagi "📈 Statistikam" tugmasi orqali o'z statistikasini oladi:
    bugungi holat, joriy oy jami, vazifalar bajarilishi va sababli kunlar."""
    user = await db.scalar(select(User).where(User.telegram_id == telegram_id))
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Foydalanuvchi topilmadi")

    today = today_local()
    month_start = today.replace(day=1)
    metric_keys = metrics_for(user)

    # Joriy oy jami (suhbat/tashrif — daily_results dan bitta so'rovda)
    sums = (
        await db.execute(
            select(
                func.coalesce(func.sum(DailyResult.conversations_count), 0),
                func.coalesce(func.sum(DailyResult.visits_count), 0),
            ).where(
                DailyResult.user_id == user.id,
                DailyResult.date >= month_start,
                DailyResult.date <= today,
            )
        )
    ).one()
    month_totals: dict[str, int] = {}
    if "suhbat" in metric_keys:
        month_totals["suhbat"] = int(sums[0])
    if "tashrif" in metric_keys:
        month_totals["tashrif"] = int(sums[1])
    if "video" in metric_keys:
        month_totals["video"] = await _confirmed_videos_count(db, user.id, month_start, today)

    # Vazifalar (joriy oyda berilganlar; created_at naive-UTC)
    start_utc, end_utc = local_range_utc_naive(month_start, today)
    tasks_total = (
        await db.scalar(
            select(func.count(TaskModel.id)).where(
                TaskModel.assigned_to == user.id,
                TaskModel.created_at >= start_utc,
                TaskModel.created_at < end_utc,
            )
        )
    ) or 0
    tasks_done = (
        await db.scalar(
            select(func.count(TaskModel.id)).where(
                TaskModel.assigned_to == user.id,
                TaskModel.status == TaskStatus.done.value,
                TaskModel.created_at >= start_utc,
                TaskModel.created_at < end_utc,
            )
        )
    ) or 0

    excused_days = (
        await db.scalar(
            select(func.count(ExcusedDay.id)).where(
                ExcusedDay.user_id == user.id,
                ExcusedDay.status == ExcusedStatus.approved.value,
                ExcusedDay.date >= month_start,
                ExcusedDay.date <= today,
            )
        )
    ) or 0

    return MyStatsOut(
        period=today.strftime("%Y-%m"),
        today=await today_metric_rows(db, user),
        month_totals=month_totals,
        tasks_done=tasks_done,
        tasks_total=tasks_total,
        excused_days=excused_days,
    )
