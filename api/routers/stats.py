import logging
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import case, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import settings
from api.deps import get_current_user, get_db, verify_bot_secret
from api.routers.norms import METRIC_LABELS, VIDEO_METRIC_TYPES, metrics_for
from api.services.daily_digest import send_daily_digest
from api.schemas import (
    LeadOperatorRow,
    LeadStageDayOut,
    LeadStageDaySummary,
    LeadStageMonthOut,
    LeadStageRow,
    MetricProgressRow,
    MyStatsOut,
)
from api.timeutil import TASHKENT_TZ, local_range_utc_naive, today_local
from crm import get_crm_adapter
from db.models import (
    DailyResult,
    DailyResultSource,
    ExcusedDay,
    ExcusedStatus,
    GroupPostConfig,
    HourlyActual,
    LeadStageDaily,
    MobilografStatus,
    MobilografVideo,
    Norm,
    OperatorCallsDaily,
    Role,
    ShortfallReason,
    TaskModel,
    TaskStatus,
    User,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/stats", tags=["stats"])


async def _current_norm(db: AsyncSession, user_id: int, metric_type: str) -> int | None:
    norm = await db.scalar(
        select(Norm)
        .where(Norm.user_id == user_id, Norm.metric_type == metric_type)
        .order_by(Norm.effective_from.desc(), Norm.created_at.desc())
        .limit(1)
    )
    return norm.value if norm else None


async def _confirmed_videos_count(
    db: AsyncSession, user_id: int, day_from: date, day_to: date, video_type: str | None = None
) -> int:
    """[day_from, day_to] mahalliy kunlar oralig'ida tasdiqlangan mobilograf
    videolar soni (sent_at bazada naive-UTC saqlanadi). `video_type` berilsa
    ("oddiy"/"dumaloq") faqat o'sha turdagi videolar hisoblanadi."""
    start_utc, end_utc = local_range_utc_naive(day_from, day_to)
    conditions = [
        MobilografVideo.user_id == user_id,
        MobilografVideo.status == MobilografStatus.confirmed.value,
        MobilografVideo.sent_at >= start_utc,
        MobilografVideo.sent_at < end_utc,
    ]
    if video_type:
        conditions.append(MobilografVideo.video_type == video_type)
    return (await db.scalar(select(func.count(MobilografVideo.id)).where(*conditions))) or 0


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

    # suhbat/tashrif CRM bog'lanishiga muhtoj — bog'lanmagan bo'lsa value doim 0
    # bo'ladi, buni "orqada qoldi" deb ko'rsatmaslik uchun alohida belgilaymiz.
    # Bugun uchun qo'lda kiritilgan yozuv bo'lsa (source=manual), CRM ID yo'q
    # bo'lsa ham haqiqiy ma'lumot bor hisoblanadi. video mobilograf orqali keladi
    # va CRM bog'lanishiga bog'liq emas.
    has_manual_today = bool(result and result.source == DailyResultSource.manual.value)
    tracked_by_key = {
        "suhbat": user.crm_external_id is not None or has_manual_today,
        "tashrif": user.crm_visit_external_id is not None or has_manual_today,
    }

    rows = []
    for key in metrics_for(user):
        if key in VIDEO_METRIC_TYPES:
            value = await _confirmed_videos_count(db, user.id, today, today, video_type=VIDEO_METRIC_TYPES[key])
        else:
            value = values.get(key, 0)
        rows.append(
            MetricProgressRow(
                key=key,
                label=METRIC_LABELS.get(key, key),
                value=value,
                norm=await _current_norm(db, user.id, key),
                tracked=tracked_by_key.get(key, True),
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
    week_start = today - timedelta(days=today.weekday())  # shu hafta dushanbasi
    metric_keys = metrics_for(user)

    async def _range_totals(day_from: date) -> dict[str, int]:
        """[day_from, bugun] oralig'i jami — lavozim ko'rsatkichlariga qarab."""
        sums = (
            await db.execute(
                select(
                    func.coalesce(func.sum(DailyResult.conversations_count), 0),
                    func.coalesce(func.sum(DailyResult.visits_count), 0),
                ).where(
                    DailyResult.user_id == user.id,
                    DailyResult.date >= day_from,
                    DailyResult.date <= today,
                )
            )
        ).one()
        totals: dict[str, int] = {}
        if "suhbat" in metric_keys:
            totals["suhbat"] = int(sums[0])
        if "tashrif" in metric_keys:
            totals["tashrif"] = int(sums[1])
        for key, video_type in VIDEO_METRIC_TYPES.items():
            if key in metric_keys:
                totals[key] = await _confirmed_videos_count(db, user.id, day_from, today, video_type=video_type)
        return totals

    week_totals = await _range_totals(week_start)
    month_totals = await _range_totals(month_start)

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
        week_totals=week_totals,
        month_totals=month_totals,
        tasks_done=tasks_done,
        tasks_total=tasks_total,
        excused_days=excused_days,
    )


# --- Lidlar statistikasi (CRM bosqichlar kesimida, kunlik snapshot) ---

LEAD_STATS_MANAGER_ROLES = {Role.hr.value, Role.rop.value, Role.boss.value, Role.dasturchi.value}


# "Tashrif" bosqichi nom bo'yicha aniqlanadi (bir necha voronkada bir xil nomli
# "Tashrif" bosqichi bo'lishi mumkin — tashkilot ko'rinishida hammasi tashrif sifatida
# sanaladi, shunda sarlavhadagi "Tashriflar" soni bosqichlar ro'yxatidagi "Tashrif"
# qatoriga mos keladi). Per-xodim KPI'dagi visit_id (CRM_UYSOT_VISIT_PIPE_STATUS_ID)
# alohida — u faqat bitta voronka uchun.
VISIT_STAGE_NAME = "tashrif"


def _can_view_lead_stats(user: User) -> bool:
    """Kimlar ko'radi: barcha rahbar rollar hamda sotuv operatorlari — lavozimida
    suhbat/tashrif ko'rsatkichi kuzatiladigan xodimlar (mobilograf kabi sotuvga
    aloqasi yo'q lavozimlar ko'rmaydi)."""
    if user.role in LEAD_STATS_MANAGER_ROLES:
        return True
    metrics = metrics_for(user)
    return "suhbat" in metrics or "tashrif" in metrics


async def _lead_stats_actor(telegram_id: int, db: AsyncSession) -> User:
    """Lidlar statistikasini ko'ra oladigan har qanday foydalanuvchi (rahbar yoki
    sotuv operatori) — shaxsiy (/me) ko'rinish uchun."""
    user = await db.scalar(select(User).where(User.telegram_id == telegram_id))
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Foydalanuvchi topilmadi")
    if not user.is_active or not _can_view_lead_stats(user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Bu amal uchun ruxsat yo'q")
    return user


async def _lead_stats_manager_actor(telegram_id: int, db: AsyncSession) -> User:
    """Faqat rahbar rollar — butun tashkilot / boshqa operatorlar ko'rinishi uchun.
    Sotuv operatorlari faqat o'z shaxsiy statistikasini (/me) ko'radi."""
    user = await db.scalar(select(User).where(User.telegram_id == telegram_id))
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Foydalanuvchi topilmadi")
    if not user.is_active or user.role not in LEAD_STATS_MANAGER_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Bu amal uchun ruxsat yo'q")
    return user


def _resolve_self_responsible_id(user: User) -> int:
    """Xodimning o'z CRM operator ID'si (`crm_visit_external_id` = Uysot
    `responsibleById`). Sozlanmagan bo'lsa — tushunarli xato."""
    if not user.crm_visit_external_id:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Sizning CRM operator ID'ingiz hali sozlanmagan — rahbaringizga murojaat qiling.",
        )
    try:
        return int(user.crm_visit_external_id)
    except (TypeError, ValueError):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "CRM operator ID'ingiz noto'g'ri formatda.")


async def _snapshot_calls(db: AsyncSession, adapter, today: date) -> int:
    """Bugungi qo'ng'iroqlarni (kiruvchi/chiquvchi) operator kesimida `operator_calls_daily`ga
    yozadi. `employeeNum` → `responsibleById` tizim foydalanuvchilarining CRM ID lari orqali
    o'giriladi; bog'lanmagan qo'ng'iroqlar `responsible_id=0` ("Boshqa") ostida jamlanadi
    (tashkilot jami to'g'ri bo'lishi uchun). CRM xatosida jadval o'zgarmaydi (-1 qaytaradi)."""
    breakdown = await adapter.get_daily_call_breakdown(today)
    if breakdown is None:
        return -1

    # employeeNum -> (responsible_id, name) — tizim foydalanuvchilaridan
    users = list(
        await db.scalars(
            select(User).where(User.crm_external_id.isnot(None), User.crm_visit_external_id.isnot(None))
        )
    )
    emp_to_operator: dict[str, tuple[int, str]] = {}
    for u in users:
        try:
            emp_to_operator[u.crm_external_id] = (int(u.crm_visit_external_id), u.full_name)
        except (TypeError, ValueError):
            continue

    # responsible_id -> {name, in, out}
    agg: dict[int, dict] = {}
    unmapped: dict[str, int] = {}  # employeeNum -> qo'ng'iroqlar soni (diagnostika)
    for employee_num, dirs in breakdown.items():
        rid, name = emp_to_operator.get(employee_num, (0, "Boshqa operatorlar"))
        if rid == 0:
            unmapped[employee_num] = dirs.get("in", 0) + dirs.get("out", 0)
        entry = agg.setdefault(rid, {"name": name, "in": 0, "out": 0})
        entry["in"] += dirs.get("in", 0)
        entry["out"] += dirs.get("out", 0)

    if unmapped:
        # Bog'lanmagan qo'ng'iroqlar "Boshqa operatorlar" (rid=0) ostiga tushadi —
        # qaysi employeeNum'lar ekani log'da ko'rinsin (CRM ID to'ldirish uchun signal).
        logger.warning(
            "CRM ID bog'lanmagan employeeNum'lar (%d ta, jami %d qo'ng'iroq): %s",
            len(unmapped),
            sum(unmapped.values()),
            ", ".join(f"{k}={v}" for k, v in sorted(unmapped.items(), key=lambda x: -x[1])),
        )

    await db.execute(delete(OperatorCallsDaily).where(OperatorCallsDaily.date == today))
    for rid, a in agg.items():
        db.add(
            OperatorCallsDaily(
                date=today,
                responsible_id=rid,
                responsible_name=a["name"],
                calls_in=a["in"],
                calls_out=a["out"],
            )
        )
    await db.commit()
    return len(agg)


async def _snapshot_lead_breakdown(db: AsyncSession) -> dict:
    """Bugungi kunning operator×bosqich (lidlar) va operator (qo'ng'iroqlar) kesimini
    CRM'dan skanerlab bazaga yozadi. Lid skaneri sekin (butun baza, bir necha daqiqa),
    qo'ng'iroq skaneri tez (call-history vaqt bo'yicha tartiblangan). CRM xatosida
    tegishli qism yozilmaydi (mavjud snapshot saqlanib qoladi). Faqat fon ishida."""
    adapter = get_crm_adapter(settings.crm_type)
    if not adapter:
        return {"synced": False, "reason": "CRM sozlanmagan"}

    today = today_local()

    # Qo'ng'iroqlar (tez) — avval, chunki lid skaneri uzoq
    calls_rows = await _snapshot_calls(db, adapter, today)

    rows = await adapter.get_daily_lead_breakdown(today)
    if rows is None:
        return {"synced": calls_rows >= 0, "reason": "Lidlarni CRM'dan olib bo'lmadi", "call_operators": calls_rows}

    await db.execute(delete(LeadStageDaily).where(LeadStageDaily.date == today))
    for row in rows:
        db.add(
            LeadStageDaily(
                date=today,
                responsible_id=row["responsible_id"],
                responsible_name=row["responsible_name"],
                pipe_status_id=row["pipe_status_id"],
                stage_name=row["stage_name"],
                leads_count=row["count"],
            )
        )
    await db.commit()
    return {"synced": True, "date": today.isoformat(), "lead_rows": len(rows), "call_operators": calls_rows}


@router.post("/lead-stages/sync", dependencies=[Depends(verify_bot_secret)])
async def sync_lead_stages(db: AsyncSession = Depends(get_db)) -> dict:
    """Scheduler tomonidan muntazam chaqiriladi — bugungi operator×bosqich kesimini
    CRM'dan to'liq skanerlab bazaga yozadi (kun davomida holat yangilanib boradi,
    oxirgi skaner kunning yakuniy holati bo'lib qoladi). Skaner sekin (rate-limitga
    rioya qilib bir necha daqiqa), shuning uchun faqat fon ishida chaqiriladi."""
    return await _snapshot_lead_breakdown(db)


async def _last_updated_for(db: AsyncSession, day_from: date, day_to: date):
    return await db.scalar(
        select(func.max(LeadStageDaily.updated_at)).where(
            LeadStageDaily.date >= day_from, LeadStageDaily.date <= day_to
        )
    )


def _is_visit_name(stage_name: str) -> bool:
    return stage_name.strip().lower() == VISIT_STAGE_NAME


async def _build_lead_month(
    db: AsyncSession, month: str | None, responsible_id: int | None = None
) -> LeadStageMonthOut:
    """Oylik ko'rinishni bazadagi snapshotdan quradi (bot va web uchun umumiy).
    `responsible_id` berilsa — faqat o'sha operatorning kunlik yig'indilari (xodim
    o'z shaxsiy statistikasini ko'rganda)."""
    today = today_local()
    month_key = month or today.strftime("%Y-%m")
    try:
        year, mon = int(month_key[:4]), int(month_key[5:7])
        month_start = date(year, mon, 1)
    except (ValueError, IndexError):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Oy formati noto'g'ri (YYYY-MM)")
    month_end = date(year + 1, 1, 1) if mon == 12 else date(year, mon + 1, 1)
    last_day = min(today, month_end - timedelta(days=1)) if month_start <= today else month_end - timedelta(days=1)

    # Kun × (lidlar jami, tashrif) — operatorlar bo'yicha yig'indi. Tashrif nom bo'yicha.
    is_visit = func.lower(func.trim(LeadStageDaily.stage_name)) == VISIT_STAGE_NAME
    lead_q = (
        select(
            LeadStageDaily.date,
            func.sum(LeadStageDaily.leads_count),
            func.sum(case((is_visit, LeadStageDaily.leads_count), else_=0)),
        )
        .where(LeadStageDaily.date >= month_start, LeadStageDaily.date < month_end)
        .group_by(LeadStageDaily.date)
        .order_by(LeadStageDaily.date)
    )
    call_q = (
        select(
            OperatorCallsDaily.date,
            func.sum(OperatorCallsDaily.calls_in + OperatorCallsDaily.calls_out),
        )
        .where(OperatorCallsDaily.date >= month_start, OperatorCallsDaily.date < month_end)
        .group_by(OperatorCallsDaily.date)
    )
    if responsible_id is not None:
        lead_q = lead_q.where(LeadStageDaily.responsible_id == responsible_id)
        call_q = call_q.where(OperatorCallsDaily.responsible_id == responsible_id)

    lead_rows = (await db.execute(lead_q)).all()
    call_rows = (await db.execute(call_q)).all()
    calls_by_day = {d: int(c) for d, c in call_rows}

    days = [
        LeadStageDaySummary(date=d, calls=calls_by_day.get(d, 0), total=int(total), visits=int(visits))
        for d, total, visits in lead_rows
    ]
    # Faqat qo'ng'iroq bo'lgan (lid snapshotisiz) kunlar ham ko'rinsin
    lead_days = {d.date for d in days}
    for d, c in calls_by_day.items():
        if d not in lead_days:
            days.append(LeadStageDaySummary(date=d, calls=c, total=0, visits=0))
    days.sort(key=lambda x: x.date)

    return LeadStageMonthOut(
        month=month_key,
        calls=sum(d.calls for d in days),
        total=sum(d.total for d in days),
        visits=sum(d.visits for d in days),
        days=days,
        last_updated=await _last_updated_for(db, month_start, last_day),
    )


async def _build_lead_day(db: AsyncSession, day: date, responsible_id: int | None) -> LeadStageDayOut:
    """Kunlik ko'rinishni bazadan quradi (bot va web uchun umumiy). `responsible_id`
    berilmasa — tashkilot jami + operatorlar ro'yxati; berilsa — bitta operator.
    Gaplashilgan (qo'ng'iroq) va lidlar bosqichlari birga qaytariladi."""
    base = select(LeadStageDaily).where(LeadStageDaily.date == day)
    call_q = select(OperatorCallsDaily).where(OperatorCallsDaily.date == day)
    if responsible_id is not None:
        base = base.where(LeadStageDaily.responsible_id == responsible_id)
        call_q = call_q.where(OperatorCallsDaily.responsible_id == responsible_id)
    records = list(await db.scalars(base))
    call_records = list(await db.scalars(call_q))

    # Bosqichlarni nom bo'yicha birlashtiramiz.
    stage_agg: dict[str, int] = {}
    for r in records:
        stage_agg[r.stage_name] = stage_agg.get(r.stage_name, 0) + r.leads_count
    stages = [
        LeadStageRow(pipe_status_id=0, stage_name=name, count=cnt)
        for name, cnt in sorted(stage_agg.items(), key=lambda x: -x[1])
    ]

    calls_in = sum(c.calls_in for c in call_records)
    calls_out = sum(c.calls_out for c in call_records)

    responsible_name = None
    operators: list[LeadOperatorRow] = []
    if responsible_id is not None:
        responsible_name = (
            (records[0].responsible_name if records else None)
            or (call_records[0].responsible_name if call_records else None)
            or str(responsible_id)
        )
    else:
        # Operatorlarni lidlar va qo'ng'iroqlardan birlashtiramiz (responsible_id bo'yicha)
        op_agg: dict[int, dict] = {}
        for r in records:
            a = op_agg.setdefault(r.responsible_id, {"name": r.responsible_name, "total": 0, "visits": 0, "cin": 0, "cout": 0})
            a["total"] += r.leads_count
            if _is_visit_name(r.stage_name):
                a["visits"] += r.leads_count
        for c in call_records:
            a = op_agg.setdefault(c.responsible_id, {"name": c.responsible_name, "total": 0, "visits": 0, "cin": 0, "cout": 0})
            a["cin"] += c.calls_in
            a["cout"] += c.calls_out
            if not a.get("name"):
                a["name"] = c.responsible_name
        operators = [
            LeadOperatorRow(
                responsible_id=rid,
                responsible_name=a["name"],
                calls=a["cin"] + a["cout"],
                calls_in=a["cin"],
                calls_out=a["cout"],
                total=a["total"],
                visits=a["visits"],
            )
            for rid, a in sorted(op_agg.items(), key=lambda x: -(x[1]["cin"] + x[1]["cout"] + x[1]["total"]))
        ]

    return LeadStageDayOut(
        date=day,
        calls=calls_in + calls_out,
        calls_in=calls_in,
        calls_out=calls_out,
        total=sum(r.leads_count for r in records),
        visits=sum(r.leads_count for r in records if _is_visit_name(r.stage_name)),
        stages=stages,
        operators=operators,
        responsible_id=responsible_id,
        responsible_name=responsible_name,
        last_updated=await _last_updated_for(db, day, day),
    )


# --- Bot endpointlari (telegram_id + bot-secret) ---


@router.get(
    "/lead-stages/{telegram_id}",
    response_model=LeadStageMonthOut,
    dependencies=[Depends(verify_bot_secret)],
)
async def lead_stage_month(
    telegram_id: int, month: str | None = None, db: AsyncSession = Depends(get_db)
) -> LeadStageMonthOut:
    """Tashkilot oylik ko'rinishi (faqat rahbarlar). Bazadagi fon-snapshotdan."""
    await _lead_stats_manager_actor(telegram_id, db)
    return await _build_lead_month(db, month)


@router.get(
    "/lead-stages/{telegram_id}/day/{day}",
    response_model=LeadStageDayOut,
    dependencies=[Depends(verify_bot_secret)],
)
async def lead_stage_day(
    telegram_id: int,
    day: date,
    responsible_id: int | None = None,
    db: AsyncSession = Depends(get_db),
) -> LeadStageDayOut:
    """Tashkilot kunlik ko'rinishi + operator kesimi (faqat rahbarlar)."""
    await _lead_stats_manager_actor(telegram_id, db)
    return await _build_lead_day(db, day, responsible_id)


# --- Shaxsiy (/me) — har bir xodim faqat o'z statistikasini ko'radi ---


@router.get(
    "/lead-stages/{telegram_id}/me",
    response_model=LeadStageMonthOut,
    dependencies=[Depends(verify_bot_secret)],
)
async def my_lead_stage_month(
    telegram_id: int, month: str | None = None, db: AsyncSession = Depends(get_db)
) -> LeadStageMonthOut:
    """Xodimning O'Z oylik lid/qo'ng'iroq statistikasi (sotuv operatorlari uchun)."""
    user = await _lead_stats_actor(telegram_id, db)
    rid = _resolve_self_responsible_id(user)
    return await _build_lead_month(db, month, responsible_id=rid)


@router.get(
    "/lead-stages/{telegram_id}/me/day/{day}",
    response_model=LeadStageDayOut,
    dependencies=[Depends(verify_bot_secret)],
)
async def my_lead_stage_day(
    telegram_id: int, day: date, db: AsyncSession = Depends(get_db)
) -> LeadStageDayOut:
    """Xodimning O'Z kunlik statistikasi (gaplashilgan + lid bosqichlari)."""
    user = await _lead_stats_actor(telegram_id, db)
    rid = _resolve_self_responsible_id(user)
    return await _build_lead_day(db, day, rid)


# --- Web endpointlari (JWT — kirgan foydalanuvchi) ---


def _require_lead_stats_web(user: User = Depends(get_current_user)) -> User:
    if not _can_view_lead_stats(user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Bu bo'lim uchun ruxsat yo'q")
    return user


def _require_lead_stats_manager_web(user: User = Depends(get_current_user)) -> User:
    if user.role not in LEAD_STATS_MANAGER_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Bu ko'rinish faqat rahbarlar uchun")
    return user


@router.get("/web/lead-stages", response_model=LeadStageMonthOut)
async def web_lead_stage_month(
    month: str | None = None,
    _: User = Depends(_require_lead_stats_manager_web),
    db: AsyncSession = Depends(get_db),
) -> LeadStageMonthOut:
    """Sayt uchun tashkilot oylik lid statistikasi (faqat rahbarlar)."""
    return await _build_lead_month(db, month)


@router.get("/web/lead-stages/day/{day}", response_model=LeadStageDayOut)
async def web_lead_stage_day(
    day: date,
    responsible_id: int | None = None,
    _: User = Depends(_require_lead_stats_manager_web),
    db: AsyncSession = Depends(get_db),
) -> LeadStageDayOut:
    """Sayt uchun tashkilot kunlik lid statistikasi + operator kesimi (faqat rahbarlar)."""
    return await _build_lead_day(db, day, responsible_id)


@router.get("/web/lead-stages/me", response_model=LeadStageMonthOut)
async def web_my_lead_stage_month(
    month: str | None = None,
    user: User = Depends(_require_lead_stats_web),
    db: AsyncSession = Depends(get_db),
) -> LeadStageMonthOut:
    """Sayt uchun xodimning O'Z oylik statistikasi."""
    rid = _resolve_self_responsible_id(user)
    return await _build_lead_month(db, month, responsible_id=rid)


@router.get("/web/lead-stages/me/day/{day}", response_model=LeadStageDayOut)
async def web_my_lead_stage_day(
    day: date,
    user: User = Depends(_require_lead_stats_web),
    db: AsyncSession = Depends(get_db),
) -> LeadStageDayOut:
    """Sayt uchun xodimning O'Z kunlik statistikasi."""
    rid = _resolve_self_responsible_id(user)
    return await _build_lead_day(db, day, rid)


# --- Sayt "Statistika" paneli: trend, operator kesimi, sabablar (faqat rahbarlar) ---

_OVERVIEW_MIN_DAYS = 7
_OVERVIEW_MAX_DAYS = 90
_REASONS_DAYS = 7
# Davr kesimi: joriy davr vs oldingi TENG uzunlikdagi davr (halol % uchun).
_SUMMARY_PERIOD_DAYS = {"today": 1, "week": 7, "month": 30}


def _parse_month_range(month: str, today: date) -> tuple[date, date]:
    """"YYYY-MM" → (oy boshi, oy oxiri) — oxiri bugundan oshmaydi (joriy oy uchun)."""
    try:
        y_s, m_s = month.split("-")
        start = date(int(y_s), int(m_s), 1)
    except (ValueError, TypeError):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "month formati: YYYY-MM")
    if start > today:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Kelajak oy uchun ma'lumot yo'q")
    next_month = date(start.year + 1, 1, 1) if start.month == 12 else date(start.year, start.month + 1, 1)
    return start, min(next_month - timedelta(days=1), today)


@router.get("/web/overview")
async def web_stats_overview(
    days: int = 30,
    month: str | None = None,
    _: User = Depends(_require_lead_stats_manager_web),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Sayt statistika paneli: kunlik trend seriyasi (qo'ng'iroq / gaplashgan vaqt /
    lid / tashrif) + sabablar. Hammasi bazadagi kunlik snapshotlardan (CRM'ga murojaat
    yo'q) — 3 ta grouped so'rov. month (YYYY-MM) berilsa — o'sha kalendar oy (days
    e'tiborga olinmaydi), sabablar ham butun oy uchun; aks holda oxirgi `days` kun,
    sabablar oxirgi 7 kun."""
    today = today_local()
    if month:
        start, end = _parse_month_range(month, today)
        days = (end - start).days + 1
    else:
        days = max(_OVERVIEW_MIN_DAYS, min(days, _OVERVIEW_MAX_DAYS))
        end = today
        start = end - timedelta(days=days - 1)

    call_rows = await db.execute(
        select(
            OperatorCallsDaily.date,
            func.sum(OperatorCallsDaily.calls_in + OperatorCallsDaily.calls_out),
        )
        .where(OperatorCallsDaily.date >= start, OperatorCallsDaily.date <= end)
        .group_by(OperatorCallsDaily.date)
    )
    is_visit = func.lower(func.trim(LeadStageDaily.stage_name)) == VISIT_STAGE_NAME
    lead_rows = await db.execute(
        select(
            LeadStageDaily.date,
            func.sum(LeadStageDaily.leads_count),
            func.sum(case((is_visit, LeadStageDaily.leads_count), else_=0)),
        )
        .where(LeadStageDaily.date >= start, LeadStageDaily.date <= end)
        .group_by(LeadStageDaily.date)
    )
    talk_rows = await db.execute(
        select(HourlyActual.date, func.sum(HourlyActual.talk_sec))
        .where(HourlyActual.date >= start, HourlyActual.date <= end)
        .group_by(HourlyActual.date)
    )

    calls_by = {d: int(v or 0) for d, v in call_rows.all()}
    leads_by = {d: (int(t or 0), int(v or 0)) for d, t, v in lead_rows.all()}
    talk_by = {d: int(v or 0) for d, v in talk_rows.all()}

    series = []
    for i in range(days):
        d = start + timedelta(days=i)
        leads, visits = leads_by.get(d, (0, 0))
        series.append(
            {
                "date": d.isoformat(),
                "calls": calls_by.get(d, 0),
                "talk_sec": talk_by.get(d, 0),
                "leads": leads,
                "visits": visits,
            }
        )

    # Sabablar — month rejimida butun oy, aks holda oxirgi 7 kun. Yangi birinchi.
    # reason NULL — operator hali yozmagan.
    reasons_start = start if month else end - timedelta(days=_REASONS_DAYS - 1)
    reason_rows = await db.execute(
        select(ShortfallReason, User.full_name)
        .join(User, User.id == ShortfallReason.user_id)
        .where(ShortfallReason.date >= reasons_start, ShortfallReason.date <= end)
        .order_by(ShortfallReason.date.desc(), ShortfallReason.hour.desc())
        .limit(200)
    )
    reasons = [
        {
            "date": r.date.isoformat(),
            "hour": r.hour,
            "user_name": full_name,
            "reason": r.reason,
            "ai_category": r.ai_category,
            "raw_text": (r.raw_text or "")[:200] or None,
            "verified": r.verified,
            "verify_note": r.verify_note,
        }
        for r, full_name in reason_rows.all()
    ]

    return {"days": days, "date_from": start.isoformat(), "date_to": end.isoformat(),
            "series": series, "reasons": reasons}


@router.get("/web/operator-summary")
async def web_operator_summary(
    period: str = "week",
    month: str | None = None,
    _: User = Depends(_require_lead_stats_manager_web),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Davr kesimida operator jadvali: qo'ng'iroq (oldingi teng davrga % farq bilan),
    gaplashgan vaqt, lid, tashrif, vazifa. period: today (bugun vs kecha) | week
    (oxirgi 7 kun vs oldingi 7) | month (oxirgi 30 kun vs oldingi 30). month (YYYY-MM)
    berilsa — o'sha kalendar oy (period e'tiborga olinmaydi), % — oldingi teng
    uzunlikdagi davrga nisbatan."""
    # Servisdagi yig'uvchilar bilan bir xil hisob — digest va sayt raqamlari mos kelsin
    from api.services.weekly_digest import _pct_change, _range_by_operator, _tasks_by_user

    today = today_local()
    if month:
        cur_start, cur_end = _parse_month_range(month, today)
        length = (cur_end - cur_start).days + 1
        period = month
    else:
        length = _SUMMARY_PERIOD_DAYS.get(period)
        if length is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "period: today | week | month")
        cur_end = today
        cur_start = cur_end - timedelta(days=length - 1)
    prev_end = cur_start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=length - 1)

    current = await _range_by_operator(db, cur_start, cur_end)
    previous = await _range_by_operator(db, prev_start, prev_end)
    tasks = await _tasks_by_user(db, cur_start, cur_end)

    talk_rows = await db.execute(
        select(HourlyActual.user_id, func.sum(HourlyActual.talk_sec))
        .where(HourlyActual.date >= cur_start, HourlyActual.date <= cur_end)
        .group_by(HourlyActual.user_id)
    )
    talk_by_user = {uid: int(v or 0) for uid, v in talk_rows.all()}

    employees = list(
        await db.scalars(
            select(User).where(User.role == Role.employee.value, User.is_active == True)  # noqa: E712
        )
    )
    user_by_rid: dict[int, User] = {}
    for u in employees:
        try:
            if u.crm_visit_external_id:
                user_by_rid[int(u.crm_visit_external_id)] = u
        except (TypeError, ValueError):
            continue

    active = {rid: a for rid, a in current.items() if a["calls"] or a["leads"]}
    operators = []
    for rid, a in sorted(active.items(), key=lambda x: -(x[1]["calls"] + x[1]["leads"])):
        user = user_by_rid.get(rid)
        prev = previous.get(rid)
        prev_calls = prev["calls"] if prev else None
        row = {
            "responsible_id": rid,
            "name": (user.full_name if user else a["name"]) or str(rid),
            "is_system_user": user is not None,
            "calls": a["calls"],
            "prev_calls": prev_calls,
            "calls_pct": _pct_change(a["calls"], prev_calls),
            "talk_sec": talk_by_user.get(user.id, 0) if user else 0,
            "leads": a["leads"],
            "visits": a["visits"],
            "tasks_done": None,
            "tasks_total": None,
        }
        if user is not None and user.id in tasks:
            row["tasks_done"], row["tasks_total"] = tasks[user.id]
        operators.append(row)

    total_calls = sum(a["calls"] for a in active.values())
    prev_total_calls = sum(a["calls"] for a in previous.values())
    active_uids = {user_by_rid[rid].id for rid in active if rid in user_by_rid}
    totals = {
        "calls": total_calls,
        "prev_calls": prev_total_calls if previous else None,
        "calls_pct": _pct_change(total_calls, prev_total_calls if previous else None),
        "talk_sec": sum(sec for uid, sec in talk_by_user.items() if uid in active_uids),
        "leads": sum(a["leads"] for a in active.values()),
        "visits": sum(a["visits"] for a in active.values()),
    }

    return {
        "period": period,
        "date_from": cur_start.isoformat(),
        "date_to": cur_end.isoformat(),
        "prev_from": prev_start.isoformat(),
        "prev_to": prev_end.isoformat(),
        "operators": operators,
        "totals": totals,
    }


# --- Guruhga kunlik digest yuborish (bitta jamlangan xabar) ---
# Eski oqim (har operatorga ALOHIDA lid xabari + alohida vazifa jadvali + alohida AI
# xulosa) api/services/daily_digest.py dagi yagona digest bilan almashtirilgan —
# guruhga endi bitta kompakt xabar tushadi, AI xulosa uning oxirida.


async def _get_group_config(db: AsyncSession) -> GroupPostConfig:
    cfg = await db.get(GroupPostConfig, 1)
    if cfg is None:
        cfg = GroupPostConfig(id=1, post_hour=19, post_minute=10)
        db.add(cfg)
        await db.commit()
        await db.refresh(cfg)
    return cfg


@router.post("/lead-stages/group-tick", dependencies=[Depends(verify_bot_secret)])
async def group_post_tick(db: AsyncSession = Depends(get_db)) -> dict:
    """Scheduler har daqiqa chaqiradi. Sozlangan vaqt YETGAN yoki O'TGAN va bugun hali
    yuborilmagan bo'lsa — kunlik digestni guruhga yuboradi. `>=` semantikasi ataylab:
    scheduler aynan sozlangan daqiqani o'tkazib yuborsa ham (restart, kechikish)
    keyingi tick'da baribir yuboriladi; `last_posted_date` qo'riqchi bir kunda ikki
    marta yuborilishdan saqlaydi."""
    cfg = await _get_group_config(db)
    now = datetime.now(TASHKENT_TZ)
    today = now.date()
    due = (now.hour, now.minute) >= (cfg.post_hour, cfg.post_minute)
    if due and cfg.last_posted_date != today:
        result = await send_daily_digest(db)
        cfg.last_posted_date = today
        # Digest ko'rsatgan jami raqamlar — ertalabki "kecha yakuni" tuzatish xabari
        # (send_yesterday_correction) yakuniy sonlarni shu bilan solishtiradi.
        totals = result.get("totals") or {}
        cfg.last_posted_calls = totals.get("calls")
        cfg.last_posted_leads = totals.get("leads")
        cfg.last_posted_visits = totals.get("visits")
        await db.commit()
        return {"fired": True, **result}
    return {"fired": False, "time": f"{cfg.post_hour:02d}:{cfg.post_minute:02d}"}


@router.get("/lead-stages/group-time/{telegram_id}", dependencies=[Depends(verify_bot_secret)])
async def get_group_time(telegram_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    cfg = await _get_group_config(db)
    return {"hour": cfg.post_hour, "minute": cfg.post_minute}


@router.post("/lead-stages/group-time", dependencies=[Depends(verify_bot_secret)])
async def set_group_time(
    telegram_id: int, hour: int, minute: int, db: AsyncSession = Depends(get_db)
) -> dict:
    """Guruhga yuborish vaqtini o'zgartirish — faqat Boshliq (yoki Dasturchi)."""
    actor = await db.scalar(select(User).where(User.telegram_id == telegram_id))
    if not actor or actor.role not in (Role.boss.value, Role.dasturchi.value):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Vaqtni faqat Boshliq o'zgartira oladi")
    if not (0 <= hour <= 23) or not (0 <= minute <= 59):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Vaqt noto'g'ri (soat 0-23, daqiqa 0-59)")
    cfg = await _get_group_config(db)
    cfg.post_hour = hour
    cfg.post_minute = minute
    await db.commit()
    return {"hour": hour, "minute": minute}
