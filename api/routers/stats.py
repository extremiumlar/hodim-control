from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import case, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import settings
from api.deps import get_current_user, get_db, verify_bot_secret
from api.routers.norms import METRIC_LABELS, metrics_for
from api.schemas import (
    LeadOperatorRow,
    LeadStageDayOut,
    LeadStageDaySummary,
    LeadStageMonthOut,
    LeadStageRow,
    MetricProgressRow,
    MyStatsOut,
)
from api.timeutil import local_range_utc_naive, today_local
from crm import get_crm_adapter
from db.models import (
    DailyResult,
    ExcusedDay,
    ExcusedStatus,
    LeadStageDaily,
    MobilografStatus,
    MobilografVideo,
    Norm,
    OperatorCallsDaily,
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
    for employee_num, dirs in breakdown.items():
        rid, name = emp_to_operator.get(employee_num, (0, "Boshqa operatorlar"))
        entry = agg.setdefault(rid, {"name": name, "in": 0, "out": 0})
        entry["in"] += dirs.get("in", 0)
        entry["out"] += dirs.get("out", 0)

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
