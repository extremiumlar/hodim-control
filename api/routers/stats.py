from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import settings
from api.deps import get_db, verify_bot_secret
from api.routers.norms import METRIC_LABELS, metrics_for
from api.schemas import (
    LeadStageDayOut,
    LeadStageDaySummary,
    LeadStageMonthOut,
    LeadStageRow,
    MetricProgressRow,
    MyStatsOut,
)
from api.timeutil import local_range_utc_naive, today_local
from crm import get_crm_adapter
from crm.config import CRM_UYSOT_VISIT_PIPE_STATUS_ID
from db.models import (
    DailyResult,
    ExcusedDay,
    ExcusedStatus,
    LeadStageDaily,
    MobilografStatus,
    MobilografVideo,
    Norm,
    Role,
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


# --- Lidlar statistikasi (CRM bosqichlar kesimida, kunlik snapshot) ---

LEAD_STATS_MANAGER_ROLES = {Role.hr.value, Role.rop.value, Role.boss.value, Role.dasturchi.value}


def _visit_status_id() -> int | None:
    return int(CRM_UYSOT_VISIT_PIPE_STATUS_ID) if CRM_UYSOT_VISIT_PIPE_STATUS_ID else None


def _can_view_lead_stats(user: User) -> bool:
    """Kimlar ko'radi: barcha rahbar rollar hamda sotuv operatorlari — lavozimida
    suhbat/tashrif ko'rsatkichi kuzatiladigan xodimlar (mobilograf kabi sotuvga
    aloqasi yo'q lavozimlar ko'rmaydi)."""
    if user.role in LEAD_STATS_MANAGER_ROLES:
        return True
    metrics = metrics_for(user)
    return "suhbat" in metrics or "tashrif" in metrics


async def _lead_stats_actor(telegram_id: int, db: AsyncSession) -> User:
    user = await db.scalar(select(User).where(User.telegram_id == telegram_id))
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Foydalanuvchi topilmadi")
    if not user.is_active or not _can_view_lead_stats(user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Bu amal uchun ruxsat yo'q")
    return user


async def _refresh_today_lead_snapshot(db: AsyncSession) -> bool:
    """Bugungi kunning bosqich-kesimini CRM'dan qayta o'qib, `lead_stage_daily`da
    yangilaydi (kunning yakuniy holati shu tarzda "muzlab" qoladi — o'tgan kunlar
    CRM'dan qayta hisoblanmaydi, chunki Uysot'da tarix yo'q). CRM xatosida `False`
    qaytaradi va mavjud snapshot saqlanib qoladi."""
    adapter = get_crm_adapter(settings.crm_type)
    if not adapter:
        return False

    today = today_local()
    rows = await adapter.get_daily_stage_counts(today)
    if rows is None:
        return False

    try:
        await db.execute(delete(LeadStageDaily).where(LeadStageDaily.date == today))
        for row in rows:
            db.add(
                LeadStageDaily(
                    date=today,
                    pipe_status_id=row["pipe_status_id"],
                    stage_name=row["stage_name"],
                    leads_count=row["count"],
                )
            )
        await db.commit()
    except IntegrityError:
        # Parallel so'rov (scheduler + bot) bir vaqtda yozdi — boshqasi allaqachon
        # yangilagan, o'qish uchun mavjud ma'lumot yetarli.
        await db.rollback()
    return True


@router.post("/lead-stages/sync", dependencies=[Depends(verify_bot_secret)])
async def sync_lead_stages(db: AsyncSession = Depends(get_db)) -> dict:
    """Bugungi bosqich-kesimini CRM'dan olib bazaga muzlatadi (kun oxiridagi holatni
    saqlash uchun). Hozircha scheduler'ga ulanmagan — talab bo'yicha (masalan kun
    yakunida qo'lda) chaqirish uchun ochiq turadi. Bundan tashqari bot statistikani
    ochganda ham bugungi kun avtomatik yangilanib saqlanadi."""
    synced = await _refresh_today_lead_snapshot(db)
    return {"synced": synced, "date": today_local().isoformat()}


@router.get(
    "/lead-stages/{telegram_id}",
    response_model=LeadStageMonthOut,
    dependencies=[Depends(verify_bot_secret)],
)
async def lead_stage_month(
    telegram_id: int, month: str | None = None, db: AsyncSession = Depends(get_db)
) -> LeadStageMonthOut:
    """Oylik ko'rinish (default — joriy oy): har kun uchun jami ishlangan lidlar va
    tashriflar. Joriy oy so'ralganda bugungi snapshot avval CRM'dan yangilanadi."""
    await _lead_stats_actor(telegram_id, db)

    today = today_local()
    month_key = month or today.strftime("%Y-%m")
    try:
        year, mon = int(month_key[:4]), int(month_key[5:7])
        month_start = date(year, mon, 1)
    except (ValueError, IndexError):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Oy formati noto'g'ri (YYYY-MM)")
    month_end = date(year + 1, 1, 1) if mon == 12 else date(year, mon + 1, 1)

    if month_start <= today < month_end:
        await _refresh_today_lead_snapshot(db)

    records = list(
        await db.scalars(
            select(LeadStageDaily)
            .where(LeadStageDaily.date >= month_start, LeadStageDaily.date < month_end)
            .order_by(LeadStageDaily.date)
        )
    )

    visit_id = _visit_status_id()
    by_day: dict[date, dict[str, int]] = {}
    for rec in records:
        day_agg = by_day.setdefault(rec.date, {"total": 0, "visits": 0})
        day_agg["total"] += rec.leads_count
        if visit_id is not None and rec.pipe_status_id == visit_id:
            day_agg["visits"] += rec.leads_count

    days = [
        LeadStageDaySummary(date=d, total=agg["total"], visits=agg["visits"])
        for d, agg in sorted(by_day.items())
    ]
    return LeadStageMonthOut(
        month=month_key,
        total=sum(d.total for d in days),
        visits=sum(d.visits for d in days),
        days=days,
    )


@router.get(
    "/lead-stages/{telegram_id}/day/{day}",
    response_model=LeadStageDayOut,
    dependencies=[Depends(verify_bot_secret)],
)
async def lead_stage_day(
    telegram_id: int, day: date, db: AsyncSession = Depends(get_db)
) -> LeadStageDayOut:
    """Bir kunning to'liq bosqich-kesimi (botda kun tanlanganda)."""
    await _lead_stats_actor(telegram_id, db)

    if day == today_local():
        await _refresh_today_lead_snapshot(db)

    records = list(
        await db.scalars(
            select(LeadStageDaily)
            .where(LeadStageDaily.date == day)
            .order_by(LeadStageDaily.leads_count.desc())
        )
    )

    visit_id = _visit_status_id()
    return LeadStageDayOut(
        date=day,
        total=sum(r.leads_count for r in records),
        visits=sum(r.leads_count for r in records if visit_id is not None and r.pipe_status_id == visit_id),
        stages=[
            LeadStageRow(pipe_status_id=r.pipe_status_id, stage_name=r.stage_name, count=r.leads_count)
            for r in records
        ],
    )
