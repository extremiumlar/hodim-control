"""Davomat (kelib-ketish) — yagona backend. Xodim web orqali GPS + Face ID bilan
Keldim/Ketdim qiladi (`/attendance/me/*`); rahbar (boss/rop/hr/dasturchi) barcha
xodimlar davomatini ko'radi va ofislarni sozlaydi. verifix (hodim_crm Django)
`attendance/views.py` dan birlashtirildi."""
import json
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user, get_db, require_roles, verify_bot_secret
from api.schemas import (
    AttendanceOut,
    EmployeeAttendanceSummary,
    LateDayEntry,
    LateStatRow,
    MeCheckRequest,
    OfficeCreate,
    OfficeOut,
    OfficeUpdate,
    RegisterFaceRequest,
    UserOut,
)
from api.services.attendance import CheckError, perform_check_in, perform_check_out
from api.timeutil import today_local
from db.models import (
    Attendance,
    AttendanceStatus,
    AuditLog,
    OfficeLocation,
    Role,
    User,
    WorkScheduleOverride,
    WorkScheduleWeekly,
)

router = APIRouter(prefix="/attendance", tags=["attendance"])

MANAGER_ROLES = (Role.hr.value, Role.rop.value, Role.boss.value, Role.dasturchi.value)


def _require_manager(user: User = Depends(get_current_user)) -> User:
    if user.role not in MANAGER_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Bu amal faqat rahbarlar uchun")
    return user


def _att_out(att: Attendance, full_name: str | None = None) -> AttendanceOut:
    return AttendanceOut(
        id=att.id,
        user_id=att.user_id,
        user_full_name=full_name,
        date=att.date,
        check_in_time=att.check_in_time,
        check_out_time=att.check_out_time,
        check_in_distance_m=att.check_in_distance_m,
        late_minutes=att.late_minutes,
        early_leave_minutes=att.early_leave_minutes,
        worked_minutes=att.worked_minutes,
        status=att.status,
        is_weekend=att.is_weekend,
        note=att.note,
    )


# ─────────────────────────────────────────────
# Xodim (kirgan foydalanuvchi) — o'z davomati
# ─────────────────────────────────────────────


@router.get("/me/today", response_model=AttendanceOut | None)
async def my_today(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> AttendanceOut | None:
    """Kirgan xodimning bugungi davomati (yo'q bo'lsa null)."""
    att = await db.scalar(
        select(Attendance).where(Attendance.user_id == user.id, Attendance.date == today_local())
    )
    return _att_out(att, user.full_name) if att else None


@router.post("/me/check-in", response_model=AttendanceOut)
async def my_check_in(
    payload: MeCheckRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AttendanceOut:
    try:
        att = await perform_check_in(
            db, user, payload.latitude, payload.longitude, payload.face_descriptor, payload.liveness
        )
    except CheckError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    return _att_out(att, user.full_name)


@router.post("/me/check-out", response_model=AttendanceOut)
async def my_check_out(
    payload: MeCheckRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AttendanceOut:
    try:
        att = await perform_check_out(
            db, user, payload.latitude, payload.longitude, payload.face_descriptor, payload.liveness
        )
    except CheckError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    return _att_out(att, user.full_name)


@router.post("/me/register-face", response_model=UserOut)
async def register_face(
    payload: RegisterFaceRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Kirgan xodim o'z yuzini ro'yxatdan o'tkazadi (128-o'lchamli deskriptor)."""
    user.face_descriptor = json.dumps(payload.face_descriptor)
    user.face_registered_at = datetime.utcnow()
    await db.commit()
    await db.refresh(user)
    return user


# ─────────────────────────────────────────────
# Rahbar — ofislar CRUD
# ─────────────────────────────────────────────


@router.get("/offices", response_model=list[OfficeOut])
async def list_offices(
    _actor: User = Depends(_require_manager), db: AsyncSession = Depends(get_db)
) -> list[OfficeLocation]:
    return list(await db.scalars(select(OfficeLocation).order_by(OfficeLocation.name)))


@router.post("/offices", response_model=OfficeOut, status_code=status.HTTP_201_CREATED)
async def create_office(
    payload: OfficeCreate, _actor: User = Depends(_require_manager), db: AsyncSession = Depends(get_db)
) -> OfficeLocation:
    office = OfficeLocation(
        name=payload.name,
        latitude=payload.latitude,
        longitude=payload.longitude,
        radius_meters=payload.radius_meters,
        is_active=payload.is_active,
    )
    db.add(office)
    await db.commit()
    await db.refresh(office)
    return office


@router.patch("/offices/{office_id}", response_model=OfficeOut)
async def update_office(
    office_id: int,
    payload: OfficeUpdate,
    _actor: User = Depends(_require_manager),
    db: AsyncSession = Depends(get_db),
) -> OfficeLocation:
    office = await db.get(OfficeLocation, office_id)
    if office is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ofis topilmadi")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(office, field, value)
    await db.commit()
    await db.refresh(office)
    return office


@router.delete("/offices/{office_id}")
async def delete_office(
    office_id: int, _actor: User = Depends(_require_manager), db: AsyncSession = Depends(get_db)
) -> dict:
    office = await db.get(OfficeLocation, office_id)
    if office is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ofis topilmadi")
    await db.delete(office)
    await db.commit()
    return {"deleted": True}


# ─────────────────────────────────────────────
# Rahbar — davomat ko'rinishlari
# ─────────────────────────────────────────────


@router.get("", response_model=list[AttendanceOut])
async def list_attendance(
    user_id: int | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    status_filter: str | None = None,
    _actor: User = Depends(_require_manager),
    db: AsyncSession = Depends(get_db),
) -> list[AttendanceOut]:
    q = select(Attendance, User.full_name).join(User, Attendance.user_id == User.id)
    if user_id is not None:
        q = q.where(Attendance.user_id == user_id)
    if date_from:
        q = q.where(Attendance.date >= date_from)
    if date_to:
        q = q.where(Attendance.date <= date_to)
    if status_filter:
        q = q.where(Attendance.status == status_filter)
    q = q.order_by(Attendance.date.desc(), Attendance.check_in_time.desc())
    rows = await db.execute(q)
    return [_att_out(att, full_name) for att, full_name in rows.all()]


@router.get("/dashboard")
async def dashboard(
    _actor: User = Depends(_require_manager), db: AsyncSession = Depends(get_db)
) -> dict:
    today = today_local()
    month_start = today.replace(day=1)

    active_users = list(await db.scalars(select(User).where(User.is_active.is_(True))))
    total_employees = len(active_users)

    today_rows = list(
        await db.execute(
            select(Attendance, User.full_name)
            .join(User, Attendance.user_id == User.id)
            .where(Attendance.date == today)
        )
    )
    checked_in_today = sum(1 for a, _ in today_rows if a.check_in_time is not None)
    present_now = sum(
        1 for a, _ in today_rows if a.check_in_time is not None and a.check_out_time is None
    )
    late_today = sum(1 for a, _ in today_rows if a.status == AttendanceStatus.late.value)
    left_today = sum(1 for a, _ in today_rows if a.check_out_time is not None)

    # Bugun ishlashi kerak bo'lganlar (ish jadvali bo'yicha) — kutilgan davomat.
    # Faqat XODIMLAR (employee) sanaladi — rahbarlar (boss/rop/hr/dasturchi)
    # davomat kutiluvchilar qatoriga kirmaydi (egasi qarori, 2026-07-15).
    # Har foydalanuvchi uchun _effective_today chaqirish N+1 so'rov bo'lardi;
    # o'rniga bugungi override'lar va shu hafta-kunidagi weekly yozuvlar bittadan
    # so'rov bilan olinadi, qoida esa ayni o'sha: override > weekly > default
    # (jadval belgilanmaganda dushanba-juma ish kuni).
    overrides_by_user = {
        o.user_id: o.is_working
        for o in await db.scalars(
            select(WorkScheduleOverride).where(WorkScheduleOverride.date == today)
        )
    }
    weekly_by_user = {
        w.user_id: w.is_working
        for w in await db.scalars(
            select(WorkScheduleWeekly).where(WorkScheduleWeekly.weekday == today.weekday())
        )
    }
    default_working = today.weekday() < 5
    employees = [u for u in active_users if u.role == Role.employee.value]
    employee_ids = {u.id for u in employees}
    working_today = sum(
        1
        for u in employees
        if overrides_by_user.get(u.id, weekly_by_user.get(u.id, default_working))
    )
    # "Kelmagan" ham xodimlar kesimida: rahbar check-in qilsa working_today'siz
    # checked_in_today'dan ayirish sonni noto'g'ri kamaytirardi.
    checked_in_employees = sum(
        1 for a, _ in today_rows if a.check_in_time is not None and a.user_id in employee_ids
    )
    not_checked_in = max(0, working_today - checked_in_employees)

    month_late = await db.scalar(
        select(func.coalesce(func.sum(Attendance.late_minutes), 0)).where(
            Attendance.date >= month_start, Attendance.date <= today
        )
    )
    month_worked = await db.scalar(
        select(func.coalesce(func.sum(Attendance.worked_minutes), 0)).where(
            Attendance.date >= month_start, Attendance.date <= today
        )
    )

    in_office = [
        {"user_name": name, "check_in_time": a.check_in_time, "late_minutes": a.late_minutes}
        for a, name in sorted(
            (r for r in today_rows if r[0].check_in_time is not None and r[0].check_out_time is None),
            key=lambda r: r[0].check_in_time,
        )
    ]
    recent = [
        {
            "user_name": name,
            "check_in_time": a.check_in_time,
            "check_out_time": a.check_out_time,
            "late_minutes": a.late_minutes,
            "status": a.status,
        }
        for a, name in sorted(
            (r for r in today_rows if r[0].check_in_time is not None),
            key=lambda r: r[0].check_in_time,
            reverse=True,
        )[:15]
    ]

    return {
        "today": today.isoformat(),
        "summary": {
            "total_employees": total_employees,
            "working_today": working_today,
            "checked_in_today": checked_in_today,
            "present_now": present_now,
            "late_today": late_today,
            "left_today": left_today,
            "not_checked_in": not_checked_in,
            "month_late_minutes": int(month_late or 0),
            "month_worked_hours": round(int(month_worked or 0) / 60, 1),
        },
        "in_office": in_office,
        "recent": recent,
    }


@router.get("/employee-summary", response_model=list[EmployeeAttendanceSummary])
async def employee_summary(
    days: int = 30, _actor: User = Depends(_require_manager), db: AsyncSession = Depends(get_db)
) -> list[EmployeeAttendanceSummary]:
    since = today_local() - timedelta(days=days)
    rows = await db.execute(
        select(
            User.id,
            User.full_name,
            func.count(Attendance.id).filter(Attendance.check_in_time.isnot(None)).label("present_days"),
            func.count(Attendance.id).filter(Attendance.status == AttendanceStatus.late.value).label("late_count"),
            func.coalesce(func.sum(Attendance.late_minutes), 0).label("late_minutes"),
            func.coalesce(func.sum(Attendance.early_leave_minutes), 0).label("early_minutes"),
            func.coalesce(func.sum(Attendance.worked_minutes), 0).label("worked_minutes"),
        )
        .join(Attendance, Attendance.user_id == User.id)
        # Faqat xodimlar — rahbarlar davomat xulosasida ko'rsatilmaydi
        # (dashboard working_today bilan bir xil qoida).
        .where(Attendance.date >= since, User.role == Role.employee.value)
        .group_by(User.id, User.full_name)
        .order_by(func.coalesce(func.sum(Attendance.late_minutes), 0).desc())
    )
    return [
        EmployeeAttendanceSummary(
            user_id=r.id,
            full_name=r.full_name,
            present_days=r.present_days,
            late_count=r.late_count,
            late_minutes=int(r.late_minutes),
            early_minutes=int(r.early_minutes),
            worked_minutes=int(r.worked_minutes),
        )
        for r in rows.all()
    ]


async def _late_stats_data(db: AsyncSession, days: int) -> list[LateStatRow]:
    """Kechikish statistikasi ma'lumoti — web (JWT) va bot (X-Bot-Secret)
    endpointlari uchun YAGONA manba. days=0 — faqat bugun."""
    since = today_local() - timedelta(days=days)
    rows = await db.execute(
        select(Attendance.user_id, User.full_name, Attendance.date, Attendance.late_minutes)
        .join(User, Attendance.user_id == User.id)
        .where(
            Attendance.date >= since,
            Attendance.late_minutes > 0,
            User.role == Role.employee.value,
        )
        .order_by(Attendance.date)
    )
    by_user: dict[int, dict] = {}
    for uid, full_name, day, late in rows.all():
        e = by_user.setdefault(
            uid, {"user_id": uid, "full_name": full_name, "days": [], "total": 0, "max": 0}
        )
        e["days"].append(LateDayEntry(date=day, late_minutes=late))
        e["total"] += late
        e["max"] = max(e["max"], late)

    out = [
        LateStatRow(
            user_id=e["user_id"],
            full_name=e["full_name"],
            late_days=len(e["days"]),
            total_late_minutes=e["total"],
            avg_late_minutes=round(e["total"] / len(e["days"]), 1),
            max_late_minutes=e["max"],
            days=e["days"],
        )
        for e in by_user.values()
    ]
    out.sort(key=lambda r: r.total_late_minutes, reverse=True)
    return out


@router.get("/late-stats", response_model=list[LateStatRow])
async def late_stats(
    days: int = 30, _actor: User = Depends(_require_manager), db: AsyncSession = Depends(get_db)
) -> list[LateStatRow]:
    """Har bir xodimning kechikish statistikasi — kunma-kun (faqat kechikkan kunlar).
    Davr: oxirgi `days` kun. employee-summary bilan bir xil qoida: faqat xodimlar
    (rahbarlar ro'yxatga kirmaydi). Jami kechikish bo'yicha kamayish tartibida."""
    return await _late_stats_data(db, days)


@router.get(
    "/late-stats-bot/{telegram_id}",
    response_model=list[LateStatRow],
    dependencies=[Depends(verify_bot_secret)],
)
async def late_stats_bot(
    telegram_id: int, days: int = 7, db: AsyncSession = Depends(get_db)
) -> list[LateStatRow]:
    """Bot uchun kechikish statistikasi («🕐 Davomat statistikasi» tugmasi).
    So'ragan telegram foydalanuvchisi rahbar (hr/rop/boss/dasturchi) bo'lishi shart."""
    user = await db.scalar(select(User).where(User.telegram_id == telegram_id))
    if not user or not user.is_active or user.role not in MANAGER_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Bu ma'lumot faqat rahbarlar uchun")
    return await _late_stats_data(db, days)


# ─────────────────────────────────────────────
# Dasturchi — davomat yozuvini o'chirish (sinov/tozalash uchun)
# ─────────────────────────────────────────────


@router.delete("/{attendance_id}")
async def delete_attendance(
    attendance_id: int,
    actor: User = Depends(require_roles(Role.dasturchi.value)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Bitta davomat yozuvini butunlay o'chiradi — faqat Dasturchi. Xodimning
    "Keldim/Ketdim" holatini tozalab, check-in oqimini qaytadan sinash uchun
    (masalan bugungi yozuvni o'chirib, yana Keldim bosish). Boshliq/HR/ROP'da bu
    huquq YO'Q — davomat tarixi ular uchun o'zgarmas hisoblanadi, faqat Dasturchi
    texnik sinov uchun o'chira oladi. Audit jurnalida saqlanadi."""
    att = await db.get(Attendance, attendance_id)
    if att is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Davomat yozuvi topilmadi")

    db.add(
        AuditLog(
            actor_id=actor.id,
            action="attendance_deleted",
            target_user_id=att.user_id,
            before={
                "date": att.date.isoformat(),
                "check_in_time": att.check_in_time.isoformat() if att.check_in_time else None,
                "check_out_time": att.check_out_time.isoformat() if att.check_out_time else None,
                "status": att.status,
            },
            after=None,
        )
    )
    await db.delete(att)
    await db.commit()
    return {"deleted": True}
