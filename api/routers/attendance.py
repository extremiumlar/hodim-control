"""Davomat (kelib-ketish) — yagona backend. Xodim web orqali GPS + Face ID bilan
Keldim/Ketdim qiladi (`/attendance/me/*`); rahbar (boss/rop/hr/dasturchi) barcha
xodimlar davomatini ko'radi va ofislarni sozlaydi. verifix (hodim_crm Django)
`attendance/views.py` dan birlashtirildi."""
import json
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import settings
from api.deps import get_current_user, get_db, require_roles, verify_bot_secret
from api.schemas import (
    AttendanceManualUpdate,
    AttendanceOut,
    AttendanceReadiness,
    EmployeeAttendanceSummary,
    FaceReregDecide,
    FaceReregOut,
    LateDayEntry,
    LateStatRow,
    MeCheckRequest,
    OfficeCreate,
    OfficeOut,
    OfficeUpdate,
    RegisterFaceOut,
    RegisterFaceRequest,
    UserOut,
)
from api.services.attendance import (
    ATTENDANCE_TRACKED_ROLES,
    CheckError,
    collect_readiness,
    find_similar_face,
    local_hm_to_utc,
    perform_check_in,
    perform_check_out,
    recompute_attendance,
)
from api.services.attendance_digest import (
    digest_tick,
    get_digest_config,
    send_attendance_digest,
)
from api.services.attendance_month import build_month_cells, parse_month
from api.notify import notify_user
from api.routers.hourly_plan import DEFAULT_START
from api.services.push import Category
from api.telegram_notify import inline_keyboard, inline_url_keyboard
from api.timeutil import TASHKENT_TZ, local_range_utc_naive, today_local
from db.models import (
    Attendance,
    AttendanceReminder,
    AttendanceStatus,
    AuditLog,
    ExcusedDay,
    ExcusedStatus,
    ExplanationRequest,
    ExplanationStatus,
    FaceReregistrationRequest,
    FaceReregStatus,
    OfficeLocation,
    Role,
    User,
    WorkScheduleOverride,
    WorkScheduleWeekly,
)

router = APIRouter(prefix="/attendance", tags=["attendance"])

MANAGER_ROLES = (Role.hr.value, Role.rop.value, Role.boss.value, Role.dasturchi.value)

# Davomat yozuvini QO'LDA tuzatish huquqi — ROP'da YO'Q. Sabab: kechikish
# daqiqalari oylik jarimasiga aylanadi, ya'ni bu endi kadrlar/pul qarori.
# ROP o'z jamoasining kechikishini ko'radi, lekin uni "tuzata" olmaydi —
# aks holda jarimani o'zi bekor qilib yuborishi mumkin bo'lardi.
ATTENDANCE_EDIT_ROLES = (Role.hr.value, Role.boss.value, Role.dasturchi.value)


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


@router.get("/me/history")
async def my_history(
    month: str | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """UX-A3: xodimning O'Z oylik davomat tarixi — kalendar kataklari + jami.

    Ilgari xodim o'z tarixini UMUMAN ko'ra olmasdi (`/me/today` xolos): "shu oy
    nechi marta kechikdim, qaysi kunlar?" degan savolga javob faqat rahbarda
    yoki jarima kelganda ma'lum bo'lardi. Har kim FAQAT o'zinikini oladi —
    `user_id` parametri ATAYLAB yo'q."""
    try:
        first, last = parse_month(month)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Oy formati «YYYY-MM» bo'lishi kerak")
    data = await build_month_cells(db, [user], first, last)
    return {
        "month": first.strftime("%Y-%m"),
        "today": today_local().isoformat(),
        "days": data[user.id]["cells"],
        "totals": data[user.id]["totals"],
    }


@router.post("/me/check-in", response_model=AttendanceOut)
async def my_check_in(
    payload: MeCheckRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AttendanceOut:
    try:
        att = await perform_check_in(
            db,
            user,
            payload.latitude,
            payload.longitude,
            payload.face_descriptor,
            payload.liveness,
            payload.accuracy,
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
            db,
            user,
            payload.latitude,
            payload.longitude,
            payload.face_descriptor,
            payload.liveness,
            payload.accuracy,
        )
    except CheckError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    return _att_out(att, user.full_name)


@router.post("/me/register-face", response_model=RegisterFaceOut)
async def register_face(
    payload: RegisterFaceRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RegisterFaceOut:
    """Kirgan xodim o'z yuzini ro'yxatdan o'tkazadi (128-o'lchamli deskriptor).

    XAVFSIZLIK (Savol A — yumshoq choralar, 2026-07-26): bu yagona joy — kimning
    yuzi qaysi hisobga bog'langanini o'zgartiradi.
    - Birinchi marta (hali yuzi yo'q): darhol yoziladi — lekin avval BOSHQA
      xodimning yuziga o'xshab ketmasligi tekshiriladi (bir xil yuz ikki hisobga
      bog'lanmasin).
    - QAYTA ro'yxatdan o'tish (allaqachon yuzi bor hisobda): darhol YOZILMAYDI —
      `FaceReregistrationRequest` sifatida kutib turadi, HR/rahbarga bot orqali
      xabar boradi, faqat ULAR tasdiqlagach descriptor almashadi. Bu — biror kimsa
      o'z JWT tokeni bilan uydan turib boshqa (yoki hatto o'z, lekin firibgar)
      descriptor yozdirib olishining oldini oladi."""
    if not user.has_face:
        dup = await find_similar_face(db, payload.face_descriptor, exclude_user_id=user.id)
        if dup is not None:
            other, sim = dup
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"Bu yuz allaqachon boshqa xodimda ro'yxatdan o'tgan ko'rinadi "
                f"(o'xshashlik {sim:.2f}). Iltimos HR/rahbarga murojaat qiling.",
            )
        user.face_descriptor = json.dumps(payload.face_descriptor)
        user.face_registered_at = datetime.utcnow()
        await db.commit()
        await db.refresh(user)
        return RegisterFaceOut(status="registered", user=UserOut.model_validate(user))

    # Qayta ro'yxatdan o'tish — rahbar tasdig'ini kutadi.
    req = FaceReregistrationRequest(
        user_id=user.id, new_descriptor=json.dumps(payload.face_descriptor)
    )
    db.add(req)
    await db.commit()
    await db.refresh(req)

    managers = list(
        await db.scalars(
            select(User).where(User.role.in_(MANAGER_ROLES), User.telegram_id.isnot(None))
        )
    )
    text = f"🧑‍💼 <b>Yuzni qayta ro'yxatdan o'tkazish so'rovi</b>\nXodim: {user.full_name}"
    keyboard = inline_keyboard(
        [[("✅ Tasdiqlayman", f"face_rereg_decide:{req.id}:approved"), ("❌ Rad etaman", f"face_rereg_decide:{req.id}:rejected")]]
    )
    for m in managers:
        # Tasdiqlash/rad etish FAQAT botda — ilovada bu ekran yo'q, shuning
        # uchun Telegram majburiy (force_telegram).
        await notify_user(
            db, m, Category.APPROVALS, text,
            reply_markup=keyboard, force_telegram=True,
        )

    return RegisterFaceOut(status="pending_approval", user=UserOut.model_validate(user))


async def _apply_face_rereg_decision(
    db: AsyncSession, item_id: int, decider: User, decision: str
) -> FaceReregOut:
    """Yuzni qayta ro'yxatdan o'tkazish so'roviga qaror — YAGONA mantiq (UX-A6).

    Ikki chaqiruvchi: bot (X-Bot-Secret, telegram_id bilan) va web (JWT).
    Ilgari faqat bot endpointi bor edi — HR botdagi xabarni o'tkazib yuborsa
    so'rov osilib qolar, webda esa faqat RO'YXAT ko'rinardi (tugmasiz)."""
    item = await db.get(FaceReregistrationRequest, item_id)
    if not item:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "So'rov topilmadi")
    if item.status != FaceReregStatus.pending.value:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Bu so'rov allaqachon hal qilingan")
    if decision not in (FaceReregStatus.approved.value, FaceReregStatus.rejected.value):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Noto'g'ri qaror")

    target = await db.get(User, item.user_id)
    if not target:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Xodim topilmadi")

    item.status = decision
    item.decided_by = decider.id
    item.decided_at = datetime.utcnow()

    if decision == FaceReregStatus.approved.value:
        new_descriptor = json.loads(item.new_descriptor)
        dup = await find_similar_face(db, new_descriptor, exclude_user_id=target.id)
        if dup is not None:
            other, sim = dup
            item.status = FaceReregStatus.rejected.value
            db.add(
                AuditLog(
                    actor_id=decider.id,
                    action="face_reregistered",
                    target_user_id=target.id,
                    before={"had_face": True},
                    after={"rejected_reason": "duplicate_face", "similar_to": other.id, "similarity": sim},
                )
            )
        else:
            target.face_descriptor = item.new_descriptor
            target.face_registered_at = datetime.utcnow()
            db.add(
                AuditLog(
                    actor_id=decider.id,
                    action="face_reregistered",
                    target_user_id=target.id,
                    before={"had_face": True},
                    after={"approved_by": decider.id, "registered_at": target.face_registered_at.isoformat()},
                )
            )
    else:
        db.add(
            AuditLog(
                actor_id=decider.id,
                action="face_reregistration_rejected",
                target_user_id=target.id,
                before={"had_face": True},
                after={"rejected_by": decider.id},
            )
        )
    await db.commit()
    await db.refresh(item)

    if target.telegram_id:
        verdict = "✅ tasdiqlandi" if item.status == FaceReregStatus.approved.value else "❌ rad etildi"
        await notify_user(
            db, target, Category.DECISIONS,
            f"Yuzni qayta ro'yxatdan o'tkazish so'rovingiz {verdict}.",
            data={"path": "/check-in"},
        )

    return FaceReregOut(
        id=item.id, user_id=item.user_id, user_full_name=target.full_name,
        status=item.status, created_at=item.created_at,
    )


@router.post("/face-reregistration/{item_id}/decide", response_model=FaceReregOut, dependencies=[Depends(verify_bot_secret)])
async def decide_face_rereregistration(
    item_id: int, payload: FaceReregDecide, db: AsyncSession = Depends(get_db)
) -> FaceReregOut:
    """Bot orqali HR/rahbar qaytadan ro'yxatdan o'tish so'rovini tasdiqlaydi/rad
    etadi. Tasdiqlansa — ENDI ham boshqa xodim yuziga o'xshab ketmasligi qayta
    tekshiriladi (so'rov yaratilgandan keyin boshqa birov shu orada ro'yxatdan
    o'tgan bo'lishi mumkin)."""
    decider = await db.scalar(select(User).where(User.telegram_id == payload.decider_telegram_id))
    if not decider or not decider.is_active or decider.role not in MANAGER_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Bu amal uchun ruxsat yo'q")
    return await _apply_face_rereg_decision(db, item_id, decider, payload.decision)


class FaceReregDecideWeb(BaseModel):
    """Web (JWT) varianti — qaror qiluvchi tokenning o'zidan olinadi."""

    decision: str  # approved | rejected


@router.post("/face-reregistration/{item_id}/decide-web", response_model=FaceReregOut)
async def decide_face_rereg_web(
    item_id: int,
    payload: FaceReregDecideWeb,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FaceReregOut:
    """UX-A6: yuz so'rovini WEBDAN hal qilish (Sozlamalar tabi). Qamrov —
    davomat tuzatish rollari (hr/boss/dasturchi): yuzni almashtirish ham
    xuddi shunday kadrlar qarori."""
    if actor.role not in ATTENDANCE_EDIT_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Bu amal uchun ruxsat yo'q")
    return await _apply_face_rereg_decision(db, item_id, actor, payload.decision)


@router.get("/face-reregistration", response_model=list[FaceReregOut])
async def list_face_reregistrations(
    status_filter: str | None = None,
    _actor: User = Depends(_require_manager),
    db: AsyncSession = Depends(get_db),
) -> list[FaceReregOut]:
    q = select(FaceReregistrationRequest).order_by(FaceReregistrationRequest.created_at.desc())
    if status_filter:
        q = q.where(FaceReregistrationRequest.status == status_filter)
    items = list(await db.scalars(q))
    user_ids = {i.user_id for i in items}
    names = {u.id: u.full_name for u in await db.scalars(select(User).where(User.id.in_(user_ids)))}
    return [
        FaceReregOut(
            id=i.id, user_id=i.user_id, user_full_name=names.get(i.user_id, "?"),
            status=i.status, created_at=i.created_at,
        )
        for i in items
    ]


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
    # Sana SATR emas, `date` obyektiga aylantirilishi SHART.
    #
    # NEGA: `Attendance.date` — DATE ustuni. SQLite'da satr bilan solishtirish
    # ishlardi (u sanani ham matn sifatida saqlaydi), PostgreSQL esa buni
    # RAD ETADI: «operator does not exist: date >= character varying». Ya'ni
    # PG'ga o'tgandan keyin bu endpoint 500 qaytara boshladi va rahbar
    # panelidagi «Yozuvlar» jadvali doim bo'sh ko'rinardi — davomatni qo'lda
    # tuzatib bo'lmaslikning ASL sababi shu edi (bosish uchun qator yo'q).
    # `/readiness` da aynan shu naqsh allaqachon to'g'ri qilingan.
    try:
        start = date.fromisoformat(date_from) if date_from else None
        end = date.fromisoformat(date_to) if date_to else None
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Sana formati «YYYY-MM-DD» bo'lishi kerak")

    q = select(Attendance, User.full_name).join(User, Attendance.user_id == User.id)
    if user_id is not None:
        q = q.where(Attendance.user_id == user_id)
    if start:
        q = q.where(Attendance.date >= start)
    if end:
        q = q.where(Attendance.date <= end)
    if status_filter:
        q = q.where(Attendance.status == status_filter)
    q = q.order_by(Attendance.date.desc(), Attendance.check_in_time.desc())
    rows = await db.execute(q)
    return [_att_out(att, full_name) for att, full_name in rows.all()]


@router.get("/dashboard")
async def dashboard(
    _actor: User = Depends(_require_manager), db: AsyncSession = Depends(get_db)
) -> dict:
    return await _dashboard_payload(db)


@router.get("/dashboard-bot/{telegram_id}", dependencies=[Depends(verify_bot_secret)])
async def dashboard_bot(telegram_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    """UX2-W4 (C5): «Bugungi holat» bot tabi — web dashboard bilan AYNAN bir
    xil hisob (late-stats-bot naqshi: X-Bot-Secret + rahbar-rol tekshiruvi)."""
    actor = await db.scalar(select(User).where(User.telegram_id == telegram_id))
    if not actor or not actor.is_active or actor.role not in MANAGER_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Bu bo'lim faqat rahbarlar uchun")
    return await _dashboard_payload(db)


async def _dashboard_payload(db: AsyncSession) -> dict:
    today = today_local()
    month_start = today.replace(day=1)

    # 3.4-band: BUTUN dashboard bir xil qamrovda bo'lishi kerak — ATTENDANCE_TRACKED_ROLES
    # (Boshliqdan tashqari hamma). Ilgari `total_employees`/`checked_in_today`/
    # `late_today` BARCHA userlardan, `working_today`/`not_checked_in` esa faqat
    # xodimlardan hisoblanardi — Boshliq check-in qilsa `checked_in_today >
    # working_today` kabi mantiqsiz holat chiqardi.
    active_users = list(await db.scalars(select(User).where(User.is_active.is_(True))))
    employees = [u for u in active_users if u.role in ATTENDANCE_TRACKED_ROLES]
    employee_ids = {u.id for u in employees}
    total_employees = len(employees)

    today_rows = list(
        await db.execute(
            select(Attendance, User.full_name)
            .join(User, Attendance.user_id == User.id)
            .where(Attendance.date == today, Attendance.user_id.in_(employee_ids))
        )
    )
    checked_in_today = sum(1 for a, _ in today_rows if a.check_in_time is not None)
    present_now = sum(
        1 for a, _ in today_rows if a.check_in_time is not None and a.check_out_time is None
    )
    late_today = sum(1 for a, _ in today_rows if a.status == AttendanceStatus.late.value)
    left_today = sum(1 for a, _ in today_rows if a.check_out_time is not None)

    # Bugun ishlashi kerak bo'lganlar (ish jadvali bo'yicha) — kutilgan davomat.
    # Har foydalanuvchi uchun _effective_today chaqirish N+1 so'rov bo'lardi;
    # o'rniga bugungi override'lar va shu hafta-kunidagi weekly yozuvlar bittadan
    # so'rov bilan olinadi, qoida esa ayni o'sha: override > weekly > default
    # (jadval belgilanmaganda dushanba-juma ish kuni).
    overrides_by_user = {
        o.user_id: o
        for o in await db.scalars(
            select(WorkScheduleOverride).where(WorkScheduleOverride.date == today)
        )
    }
    weekly_by_user = {
        w.user_id: w
        for w in await db.scalars(
            select(WorkScheduleWeekly).where(WorkScheduleWeekly.weekday == today.weekday())
        )
    }
    default_working = today.weekday() < 5

    def _works_today(u: User) -> bool:
        row = overrides_by_user.get(u.id) or weekly_by_user.get(u.id)
        if row is not None:
            return bool(row.is_working)
        return default_working

    def _start_today(u: User) -> str:
        """Bugungi jadval boshlanishi ("Kelmagan" ro'yxatida ko'rsatiladi)."""
        row = overrides_by_user.get(u.id) or weekly_by_user.get(u.id)
        if row is not None and row.is_working and row.start_time:
            return row.start_time
        return DEFAULT_START

    working_today = sum(1 for u in employees if _works_today(u))
    not_checked_in = max(0, working_today - checked_in_today)

    # UX-A1: "Kelmagan: 2" degan quruq son o'rniga ISMLAR — rahbarning ertalabki
    # asosiy savoli "kim kelmadi?" shu ro'yxat bilan javob topadi. Tasdiqlangan
    # sababli kunlilar `not_come`ga KIRMAYDI (ular kutilmayapti) — alohida
    # `excused_today` ro'yxatida.
    excused_ids = {
        e.user_id
        for e in await db.scalars(
            select(ExcusedDay).where(
                ExcusedDay.date == today, ExcusedDay.status == ExcusedStatus.approved.value
            )
        )
    }
    checked_ids = {a.user_id for a, _ in today_rows if a.check_in_time is not None}
    not_come = sorted(
        (
            {
                "user_id": u.id,
                "full_name": u.full_name,
                "schedule_start": _start_today(u),
                "telegram_linked": u.telegram_id is not None,
            }
            for u in employees
            if _works_today(u) and u.id not in checked_ids and u.id not in excused_ids
        ),
        key=lambda r: r["full_name"],
    )
    excused_today = sorted(
        (
            {"user_id": u.id, "full_name": u.full_name}
            for u in employees
            if _works_today(u) and u.id not in checked_ids and u.id in excused_ids
        ),
        key=lambda r: r["full_name"],
    )
    left = [
        {
            "user_id": a.user_id,
            "full_name": name,
            "check_in_time": a.check_in_time,
            "check_out_time": a.check_out_time,
            "worked_minutes": a.worked_minutes,
        }
        for a, name in sorted(
            (r for r in today_rows if r[0].check_out_time is not None),
            key=lambda r: r[0].check_out_time,
            reverse=True,
        )
    ]

    # Bugun DAM OLISHDAGILAR — alohida ro'yxat. Hisob-kitobga TA'SIR QILMAYDI.
    on_day_off = sorted(
        ({"user_id": u.id, "full_name": u.full_name} for u in employees if not _works_today(u)),
        key=lambda r: r["full_name"],
    )

    month_late = await db.scalar(
        select(func.coalesce(func.sum(Attendance.late_minutes), 0)).where(
            Attendance.date >= month_start, Attendance.date <= today, Attendance.user_id.in_(employee_ids)
        )
    )
    month_worked = await db.scalar(
        select(func.coalesce(func.sum(Attendance.worked_minutes), 0)).where(
            Attendance.date >= month_start, Attendance.date <= today, Attendance.user_id.in_(employee_ids)
        )
    )

    # UX2-W1 (B17): user_id barcha ro'yxatlarda — frontend ismni bosiladigan
    # qiladi (EmployeeDrawer/profil). Eski frontend ortiqcha maydonni bilmaydi.
    in_office = [
        {
            "user_id": a.user_id,
            "user_name": name,
            "check_in_time": a.check_in_time,
            "late_minutes": a.late_minutes,
        }
        for a, name in sorted(
            (r for r in today_rows if r[0].check_in_time is not None and r[0].check_out_time is None),
            key=lambda r: r[0].check_in_time,
        )
    ]
    recent = [
        {
            "user_id": a.user_id,
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

    # UX2-W1 (A4): «kim kechikdi?» — ismma-ism, eng katta kechikish tepada.
    # `in_office`dan farqi: ketib bo'lganlar ham kiradi (ular ham kechikkan edi).
    late_list = [
        {
            "user_id": a.user_id,
            "user_name": name,
            "check_in_time": a.check_in_time,
            "late_minutes": a.late_minutes,
            "left": a.check_out_time is not None,
        }
        for a, name in sorted(
            (r for r in today_rows if (r[0].late_minutes or 0) > 0),
            key=lambda r: r[0].late_minutes or 0,
            reverse=True,
        )
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
            "on_day_off": len(on_day_off),
            "month_late_minutes": int(month_late or 0),
            "month_worked_hours": round(int(month_worked or 0) / 60, 1),
        },
        "in_office": in_office,
        "recent": recent,
        "on_day_off": on_day_off,
        # UX-A1 qo'shimchalari — eski frontend bu maydonlarni bilmaydi, e'tiborsiz
        # qoldiradi (orqaga moslik buzilmaydi).
        "not_come": not_come,
        "excused_today": excused_today,
        "left": left,
        "late_list": late_list,
    }


async def _send_reminder(db: AsyncSession, actor: User, target: User) -> tuple[bool, str, int]:
    """Bitta xodimga «hali kelmadingiz» eslatmasi. (ok, xabar, bugungi_soni)
    qaytaradi — remind/{id} HTTPException'ga o'raydi, remind-all natija yig'adi.

    Spam himoyasi: bitta xodimga kuniga ko'pi bilan 2 ta (AuditLog'dagi
    `attendance_reminder_sent` yozuvlari sanaladi — yangi jadval kerak emas,
    iz baribir auditda qolishi kerak edi).

    UX2-W4 (C6/C7/C2): matn ayblovsiz va kim eslatgani bilan; jadval topilmasa
    "jadvalingiz: None" chiqmaydi; xabarga «Keldim qilish» URL tugmasi
    qo'shildi; force_telegram — jarimaga ta'sir qiladigan yagona eslatma
    push'da yo'qolib qolmasligi kerak (tushuntirish xati bilan bir qoida)."""
    if target.role not in ATTENDANCE_TRACKED_ROLES:
        return False, "Bu rol uchun davomat kuzatuvi yoqilmagan", 0

    today = today_local()
    att = await db.scalar(
        select(Attendance).where(Attendance.user_id == target.id, Attendance.date == today)
    )
    if att is not None and att.check_in_time is not None:
        return False, "allaqachon «Keldim» qilgan", 0

    day_start, day_end = local_range_utc_naive(today, today)
    sent_today = await db.scalar(
        select(func.count(AuditLog.id)).where(
            AuditLog.action == "attendance_reminder_sent",
            AuditLog.target_user_id == target.id,
            AuditLog.created_at >= day_start,
            AuditLog.created_at < day_end,
        )
    )
    if (sent_today or 0) >= 2:
        return False, "bugun allaqachon 2 marta eslatilgan", int(sent_today or 0)

    # Bugungi jadval boshlanishini eslatma matnida ko'rsatamiz.
    from api.routers.hourly_plan import _effective_today  # circular importdan qochish

    _, sched_start, _ = await _effective_today(db, target, today)
    sched_line = f" Bugungi ish vaqtingiz {sched_start}da boshlangan." if sched_start else ""
    result = await notify_user(
        db,
        target,
        Category.ATTENDANCE_REMINDER,
        f"👋 {actor.full_name} eslatmoqda: «Keldim» hali qayd etilmagan.{sched_line}\n"
        "Sabab bo'lsa — «Sababli kun so'rash» tugmasidan foydalaning.",
        reply_markup=inline_url_keyboard(
            [[("✅ Keldim qilish", f"{settings.frontend_url}/check-in")]]
        ),
        data={"path": "/check-in"},
        force_telegram=True,
    )
    if not (result.get("push") or result.get("telegram")):
        return False, "yetkazib bo'lmadi — botga ulanmagan va push yoqmagan", int(sent_today or 0)

    db.add(
        AuditLog(
            actor_id=actor.id,
            action="attendance_reminder_sent",
            target_user_id=target.id,
            before=None,
            after={"schedule_start": sched_start, "manual": True},
        )
    )
    await db.commit()
    return True, "", int(sent_today or 0) + 1


@router.post("/remind/{user_id}")
async def remind_employee(
    user_id: int,
    actor: User = Depends(_require_manager),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """UX-A5: "Bugun" tabidagi «Eslatish» tugmasi — kelmagan xodimga bot/push
    orqali shaxsiy eslatma. Ilgari rahbar faqat digestni kutar yoki qo'lda
    telefon qilardi."""
    target = await db.get(User, user_id)
    if target is None or not target.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Xodim topilmadi")

    ok, reason, sent_today = await _send_reminder(db, actor, target)
    if not ok:
        # Eski HTTP semantika saqlanadi: limit → 429, qolganlari → 400.
        code = (
            status.HTTP_429_TOO_MANY_REQUESTS
            if "2 marta" in reason
            else status.HTTP_400_BAD_REQUEST
        )
        # Matnlar eski frontend kutgan shaklga yaqin qolsin
        detail = {
            "allaqachon «Keldim» qilgan": "Xodim allaqachon «Keldim» qilgan",
            "bugun allaqachon 2 marta eslatilgan": "Bugun allaqachon 2 marta eslatilgan",
            "yetkazib bo'lmadi — botga ulanmagan va push yoqmagan":
                "Xodimga yetkazib bo'lmadi — u Telegram botga ulanmagan va push yoqmagan",
        }.get(reason, reason)
        raise HTTPException(code, detail)
    return {"sent": True, "sent_today": sent_today}


@router.post("/remind-all")
async def remind_all_employees(
    actor: User = Depends(_require_manager),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """UX2-W1 (A12): bugun kelmagan BARCHAGA bitta bosishda eslatma.
    Har xodim uchun xuddi /remind/{id} qoidalari (2/kun limiti, sababli
    kunlilarga tegilmaydi — ular "kutilmayapti"); natija bitta xulosa:
    {sent: N, failed: [{full_name, reason}]}."""
    today = today_local()
    active_users = list(await db.scalars(select(User).where(User.is_active.is_(True))))
    employees = [u for u in active_users if u.role in ATTENDANCE_TRACKED_ROLES]

    checked_ids = {
        a.user_id
        for a in await db.scalars(
            select(Attendance).where(
                Attendance.date == today, Attendance.check_in_time.isnot(None)
            )
        )
    }
    excused_ids = {
        e.user_id
        for e in await db.scalars(
            select(ExcusedDay).where(
                ExcusedDay.date == today, ExcusedDay.status == ExcusedStatus.approved.value
            )
        )
    }

    overrides_by_user = {
        o.user_id: o
        for o in await db.scalars(
            select(WorkScheduleOverride).where(WorkScheduleOverride.date == today)
        )
    }
    weekly_by_user = {
        w.user_id: w
        for w in await db.scalars(
            select(WorkScheduleWeekly).where(WorkScheduleWeekly.weekday == today.weekday())
        )
    }
    default_working = today.weekday() < 5

    def _works_today(u: User) -> bool:
        row = overrides_by_user.get(u.id) or weekly_by_user.get(u.id)
        if row is not None:
            return bool(row.is_working)
        return default_working

    targets = [
        u
        for u in employees
        if _works_today(u) and u.id not in checked_ids and u.id not in excused_ids
    ]

    sent = 0
    failed: list[dict] = []
    for target in targets:
        ok, reason, _n = await _send_reminder(db, actor, target)
        if ok:
            sent += 1
        else:
            failed.append({"full_name": target.full_name, "reason": reason})

    return {"total": len(targets), "sent": sent, "failed": failed}


@router.get("/matrix")
async def attendance_matrix(
    month: str | None = None,
    user_id: int | None = None,
    _actor: User = Depends(_require_manager),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """UX-A2: oylik davomat matritsasi — qatorlar xodimlar, ustunlar kunlar.

    300-qatorlik flat "Yozuvlar" ro'yxati oylik manzarani bermasdi; bu endpoint
    butun oyni BITTA so'rovda beradi va yozuvsiz kunlarning ma'nosini (kelmagan /
    dam / sababli / kelajak) jadval bilan birlashtirib hal qiladi — frontend
    buni o'zi qura olmasdi. `user_id` filtri — xodim profili sahifasi bitta
    qatorni olishi uchun (alohida endpoint o'rniga)."""
    try:
        first, last = parse_month(month)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Oy formati «YYYY-MM» bo'lishi kerak")

    q = select(User).where(User.is_active.is_(True), User.role.in_(ATTENDANCE_TRACKED_ROLES))
    if user_id is not None:
        q = q.where(User.id == user_id)
    users = sorted(await db.scalars(q), key=lambda u: u.full_name)
    data = await build_month_cells(db, users, first, last)
    return {
        "month": first.strftime("%Y-%m"),
        "today": today_local().isoformat(),
        "days": [(first + timedelta(days=i)).isoformat() for i in range((last - first).days + 1)],
        "employees": [
            {"user_id": u.id, "full_name": u.full_name, **data[u.id]} for u in users
        ],
    }


def _resolve_period(
    days: int, date_from: str | None, date_to: str | None
) -> tuple[date, date]:
    """UX-A4: `days` oynasi YOKI aniq davr — ikkala hisobot endpointi uchun bitta
    qoida. `date_from`/`date_to` berilsa ular ustun (kalendar oyni so'rash mumkin
    bo'ladi); berilmasa hozirgidek "oxirgi N kun" (4.6-band semantikasi)."""
    try:
        start = date.fromisoformat(date_from) if date_from else None
        end = date.fromisoformat(date_to) if date_to else None
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Sana formati «YYYY-MM-DD» bo'lishi kerak")
    if start and end:
        if end < start:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "«date_to» «date_from» dan oldin bo'lmasin")
        return start, end
    if start or end:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "date_from va date_to birga berilishi kerak"
        )
    today = today_local()
    return today - timedelta(days=days - 1), today


@router.get("/employee-summary", response_model=list[EmployeeAttendanceSummary])
async def employee_summary(
    days: int = 30,
    date_from: str | None = None,
    date_to: str | None = None,
    _actor: User = Depends(_require_manager),
    db: AsyncSession = Depends(get_db),
) -> list[EmployeeAttendanceSummary]:
    since, until = _resolve_period(days, date_from, date_to)
    # OUTER JOIN — hech qachon check-in qilmagan xodim ham natijaga kirsin
    # (0 kun, 0 daqiqa bilan). DIQQAT: sana filtri JOIN shartiga (ON) qo'yilgan,
    # WHERE'ga EMAS — WHERE'da bo'lsa NULL qatorlarni kesib, LEFT JOIN yana
    # INNER'ga aylanib qolar edi va muammo saqlanib qolardi.
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
        .select_from(User)
        .outerjoin(
            Attendance,
            and_(
                Attendance.user_id == User.id,
                Attendance.date >= since,
                Attendance.date <= until,
            ),
        )
        # Boshliqdan tashqari hamma (ATTENDANCE_TRACKED_ROLES) — dashboard va
        # guruh digesti bilan bir xil qoida.
        .where(User.role.in_(ATTENDANCE_TRACKED_ROLES), User.is_active.is_(True))
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


async def _late_stats_data(
    db: AsyncSession, days: int, date_from: str | None = None, date_to: str | None = None
) -> list[LateStatRow]:
    """Kechikish statistikasi ma'lumoti — web (JWT) va bot (X-Bot-Secret)
    endpointlari uchun YAGONA manba. days=0 — faqat bugun; UX-A4: aniq davr
    (`date_from`/`date_to`) berilsa u ustun."""
    since, until = _resolve_period(days, date_from, date_to)
    rows = await db.execute(
        select(Attendance.user_id, User.full_name, Attendance.date, Attendance.late_minutes)
        .join(User, Attendance.user_id == User.id)
        .where(
            Attendance.date >= since,
            Attendance.date <= until,
            Attendance.late_minutes > 0,
            User.role.in_(ATTENDANCE_TRACKED_ROLES),
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
    days: int = 30,
    date_from: str | None = None,
    date_to: str | None = None,
    _actor: User = Depends(_require_manager),
    db: AsyncSession = Depends(get_db),
) -> list[LateStatRow]:
    """Har bir xodimning kechikish statistikasi — kunma-kun (faqat kechikkan kunlar).
    Davr: oxirgi `days` kun YOKI aniq `date_from`/`date_to` (UX-A4 — kalendar oy).
    employee-summary bilan bir xil qoida: ATTENDANCE_TRACKED_ROLES
    (Boshliqdan tashqari hamma — HR/ROP/dasturchi ham kiradi, faqat Boshliq yo'q).
    Jami kechikish bo'yicha kamayish tartibida."""
    return await _late_stats_data(db, days, date_from, date_to)


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


@router.post("/digest", dependencies=[Depends(verify_bot_secret)])
async def attendance_digest(
    kind: str = "morning",
    telegram_id: int | None = None,
    chat_id: int | None = None,
    dry_run: bool = False,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Kunlik davomat digestini guruhga yuboradi (scheduler/cron chaqiradi).

    kind=morning — ertalabki (kim keldi/kechikdi/hali yo'q);
    kind=evening — kun yakuni (ish vaqti, kechikish, chiqmaganlar, kelmaganlar).
    dry_run=true — yubormasdan matnni qaytaradi (sinov uchun).

    XAVFSIZLIK: ixtiyoriy `chat_id` ga yuborish faqat RAHBAR nomidan mumkin —
    `telegram_id` ham berilishi va u rahbarga tegishli bo'lishi shart. Aks holda
    bot sekretini bilgan har kim butun jamoa davomatini (ismlar, kelish vaqtlari,
    kechikishlar) o'zining shaxsiy chatiga yuborib olardi. `chat_id`siz chaqiruv
    (cron/scheduler) faqat sozlangan guruhlarga boradi — u xavfsiz."""
    if chat_id is not None:
        if telegram_id is None:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "chat_id bilan yuborish uchun telegram_id ham kerak",
            )
        actor = await db.scalar(select(User).where(User.telegram_id == telegram_id))
        if not actor or not actor.is_active or actor.role not in MANAGER_ROLES:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "Tanlangan chatga yuborish faqat rahbarlar uchun"
            )
    return await send_attendance_digest(db, kind=kind, chat_id=chat_id, dry_run=dry_run)


@router.post("/digest-tick", dependencies=[Depends(verify_bot_secret)])
async def attendance_digest_tick(db: AsyncSession = Depends(get_db)) -> dict:
    """Cron har daqiqa chaqiradi — sozlangan vaqt yetgan bo'lsa digestni yuboradi."""
    return await digest_tick(db)


@router.get("/digest-time/{telegram_id}", dependencies=[Depends(verify_bot_secret)])
async def get_digest_time(telegram_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    """Bot uchun: joriy digest vaqtlari (rahbarlar ko'ra oladi)."""
    user = await db.scalar(select(User).where(User.telegram_id == telegram_id))
    if not user or not user.is_active or user.role not in MANAGER_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Bu ma'lumot faqat rahbarlar uchun")
    cfg = await get_digest_config(db)
    return {
        "morning": f"{cfg.morning_hour:02d}:{cfg.morning_minute:02d}",
        "evening": f"{cfg.evening_hour:02d}:{cfg.evening_minute:02d}",
        "morning_enabled": cfg.morning_enabled,
        "evening_enabled": cfg.evening_enabled,
    }


@router.post("/digest-time", dependencies=[Depends(verify_bot_secret)])
async def set_digest_time(
    telegram_id: int,
    kind: str,
    hour: int | None = None,
    minute: int | None = None,
    enabled: bool | None = None,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Bot uchun: digest vaqtini/yoqilganligini o'zgartirish (faqat Boshliq/Dasturchi).
    kind: morning | evening. `hour`/`minute` berilsa vaqt, `enabled` berilsa
    yoqiq-o'chiq holati yangilanadi."""
    user = await db.scalar(select(User).where(User.telegram_id == telegram_id))
    if not user or not user.is_active or user.role not in (Role.boss.value, Role.dasturchi.value):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Vaqtni faqat Boshliq o'zgartira oladi")
    if kind not in ("morning", "evening"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "kind: morning yoki evening")
    if hour is not None and not (0 <= hour <= 23):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Soat 0-23 oralig'ida bo'lsin")
    if minute is not None and not (0 <= minute <= 59):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Daqiqa 0-59 oralig'ida bo'lsin")

    cfg = await get_digest_config(db)
    if hour is not None and minute is not None:
        old_hm = (getattr(cfg, f"{kind}_hour"), getattr(cfg, f"{kind}_minute"))
        setattr(cfg, f"{kind}_hour", hour)
        setattr(cfg, f"{kind}_minute", minute)
        # 5.4-band: qo'riqchi FAQAT vaqt OLDINGA (kechroqqa) surilganda tozalanadi.
        # Ilgari HAR qanday o'zgarishda tozalanardi — masalan bugun 22:00'da
        # digest allaqachon yuborilgan bo'lsa-yu, Boshliq vaqtni 21:00'ga
        # (ORQAGA) o'zgartirsa, tozalangan qo'riqchi + "(hozir 22:30) >= (21:00)"
        # shartini darhol qanoatlantirib, digest o'sha kuni IKKINCHI marta
        # yuborilib ketardi.
        if (hour, minute) > old_hm:
            setattr(cfg, f"{kind}_last_posted", None)
    if enabled is not None:
        setattr(cfg, f"{kind}_enabled", enabled)
    await db.commit()
    await db.refresh(cfg)
    return {
        "morning": f"{cfg.morning_hour:02d}:{cfg.morning_minute:02d}",
        "evening": f"{cfg.evening_hour:02d}:{cfg.evening_minute:02d}",
        "morning_enabled": cfg.morning_enabled,
        "evening_enabled": cfg.evening_enabled,
    }


# ─────────────────────────────────────────────
# HR/Boshliq — qo'lda tuzatish va ma'lumot tayyorligi
# ─────────────────────────────────────────────


@router.get("/readiness", response_model=AttendanceReadiness)
async def attendance_readiness(
    date_from: str | None = None,
    date_to: str | None = None,
    _actor: User = Depends(_require_manager),
    db: AsyncSession = Depends(get_db),
) -> AttendanceReadiness:
    """Davr bo'yicha davomat ma'lumotining tayyorligi: jadvalsiz xodimlar,
    yopilmagan «Ketdim»lar, avtomatik yopilgan kunlar, hal qilinmagan sababli
    kunlar, yuzsiz xodimlar. Default davr — joriy oy boshidan bugungacha.

    Oylik/jarima hisobidan OLDIN ko'riladi: bu ro'yxat bo'sh bo'lmasa, hisob
    taxminlar ustiga qurilgan bo'ladi."""
    today = today_local()
    try:
        start = date.fromisoformat(date_from) if date_from else today.replace(day=1)
        end = date.fromisoformat(date_to) if date_to else today
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Sana formati «YYYY-MM-DD» bo'lishi kerak")
    if end < start:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "«date_to» «date_from» dan oldin bo'lmasin")

    return AttendanceReadiness(**await collect_readiness(db, start, end))


async def apply_manual_attendance(
    db: AsyncSession, payload: AttendanceManualUpdate, target: User
) -> tuple[Attendance, dict, bool]:
    """Davomat yozuvini yaratadi/tuzatadi va qayta hisoblaydi — AUDITSIZ, commitsiz.

    Ikki chaqiruvchi bor va ular audit bo'yicha ATAYLAB farq qiladi:
    - `manual_attendance` (bu fayl) — audit YOZADI (HR/Boshliq va shaxsan
      ruxsat berilgan odamlar; egasi "ularning auditlari saytda ko'rinib
      tursin" dedi);
    - `admin_override.admin_manual_attendance` — audit YOZMAYDI (Dasturchi,
      egasining aniq talabi: "auditlarga tushmasdan").

    Umumiy mantiq shu yerda turadi, aks holda ikki joyda takrorlanib,
    biri (masalan `recompute_attendance` chaqiruvi) unutilib qolardi.
    Qaytaradi: (yozuv, o'zgarishdan OLDINGI holat, yangi yaratildimi)."""
    if target.role not in ATTENDANCE_TRACKED_ROLES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Bu rol uchun davomat kuzatuvi yoqilmagan")
    if payload.date > today_local():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Kelajakdagi kunni tuzatib bo'lmaydi")
    if payload.check_out and not payload.check_in:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "«Ketdim» ni «Keldim» siz belgilab bo'lmaydi")

    check_in_utc = local_hm_to_utc(payload.date, payload.check_in) if payload.check_in else None
    check_out_utc = local_hm_to_utc(payload.date, payload.check_out) if payload.check_out else None
    if check_in_utc and check_out_utc and check_out_utc <= check_in_utc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "«Ketdim» vaqti «Keldim» dan keyin bo'lishi kerak")

    att = await db.scalar(
        select(Attendance).where(Attendance.user_id == target.id, Attendance.date == payload.date)
    )
    created = att is None
    if att is None:
        att = Attendance(user_id=target.id, date=payload.date)
        db.add(att)

    before = {
        "check_in_time": att.check_in_time.isoformat() if att.check_in_time else None,
        "check_out_time": att.check_out_time.isoformat() if att.check_out_time else None,
        "late_minutes": att.late_minutes,
        "worked_minutes": att.worked_minutes,
        "status": att.status,
        "note": att.note,
    }

    att.check_in_time = check_in_utc
    att.check_out_time = check_out_utc
    if payload.note is not None:
        att.note = payload.note or None
    # Qo'lda kiritilgan vaqtda GPS o'lchovi yo'q — eski masofa yangi vaqtga
    # tegishli emas, shuning uchun tozalanadi (aks holda "ofisdan 12 m" degan
    # raqam soxta ishonch berardi).
    att.check_in_distance_m = None
    att.check_in_lat = att.check_in_lng = None
    att.check_out_lat = att.check_out_lng = None

    await recompute_attendance(db, att, target)
    return att, before, created


def can_edit_attendance_records(actor: User) -> bool:
    """Roli bo'yicha (hr/boss/dasturchi) YOKI shaxsan berilgan bayroq bilan."""
    return actor.role in ATTENDANCE_EDIT_ROLES or bool(actor.can_edit_attendance)


@router.put("/manual", response_model=AttendanceOut)
async def manual_attendance(
    payload: AttendanceManualUpdate,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AttendanceOut:
    """Bir kunlik davomat yozuvini QO'LDA tuzatadi yoki yaratadi (HR/Boshliq).

    Nima uchun kerak: Face ID yoki GPS ishlamay qolsa, xodim «Keldim» bosa
    olmaydi va tizimda "kelmagan" bo'lib qoladi. Kechikish daqiqalari oylik
    jarimasiga aylanadigan bo'lgach, bunday har bir xato real nizoga aylanadi.
    Ilgari bu holatni faqat Dasturchi, faqat butunlay O'CHIRISH orqali "tuzata"
    olardi — ya'ni ma'lumotni yo'qotish evaziga.

    Vaqtlar mahalliy "HH:MM" ko'rinishida keladi; `late_minutes`/`worked_minutes`
    kiritilmaydi — ular o'sha kungi ish jadvalidan qayta hisoblanadi
    (`recompute_attendance`), shu sababli check-in oqimi bilan bir xil qoida
    qo'llanadi. Sabab MAJBURIY va audit jurnaliga tushadi.

    Ruxsat: roli bo'yicha (hr/boss/dasturchi) YOKI shaxsan berilgan
    `can_edit_attendance` bayrog'i bilan. Bayroq bilan kelganlar O'Z
    yozuvini tuzata OLMAYDI — o'z kechikishini o'chirib, jarimadan qutulib
    qolmasligi uchun (egasining aniq sharti: "barcha xodimlar lekin
    o'zinikini emas")."""
    if not can_edit_attendance_records(actor):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Bu amal uchun ruxsat yo'q")
    if actor.role not in ATTENDANCE_EDIT_ROLES and payload.user_id == actor.id:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "O'z davomat yozuvingizni o'zingiz tuzata olmaysiz"
        )

    target = await db.get(User, payload.user_id)
    if target is None or not target.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Xodim topilmadi")

    att, before, created = await apply_manual_attendance(db, payload, target)

    db.add(
        AuditLog(
            actor_id=actor.id,
            action="attendance_manual_edit",
            target_user_id=target.id,
            before=None if created else before,
            after={
                "date": payload.date.isoformat(),
                "check_in": payload.check_in,
                "check_out": payload.check_out,
                "late_minutes": att.late_minutes,
                "worked_minutes": att.worked_minutes,
                "status": att.status,
                "note": att.note,
                "reason": payload.reason,
                "created": created,
            },
        )
    )
    await db.commit()
    await db.refresh(att)
    return _att_out(att, target.full_name)


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


# ─────────────────────────────────────────────
# «Keldim/Ketdim bosishni unutmang» eslatmasi (scheduler)
# ─────────────────────────────────────────────


class AttendanceReminderTick(BaseModel):
    """Scheduler tick. `dry_run` — hech kimga YUBORMASDAN kimga ketishini
    qaytaradi (sinov uchun; test.py real xodimga xabar yubormasligi kerak)."""

    dry_run: bool = False


@router.post("/reminder-tick", dependencies=[Depends(verify_bot_secret)])
async def attendance_reminder_tick(
    payload: AttendanceReminderTick, db: AsyncSession = Depends(get_db)
) -> dict:
    """Ish oynasi boshlanishiga/tugashiga 10 daqiqa, 5 daqiqa qolganda va AYNI
    VAQTIDA «Keldim»/«Ketdim» bosmaganlarga eslatma yuboradi.

    NEGA KERAK: xodim bosishni unutsa, tizimda "kelmagan" bo'lib qoladi va bu
    to'g'ridan-to'g'ri oylik jarimasiga aylanadi. Keyin uni qo'lda tuzatish
    kerak bo'ladi (`/attendance/manual`) — eslatma o'sha ishning oldini oladi.

    QAT'IY CHETLAB O'TILADI (aks holda eslatma bezor qiladi va ishonchni
    yo'qotadi):
      - dam kunidagilar (`_effective_today` -> is_working=False);
      - tasdiqlangan sababli kundagilar (`is_excused_day`);
      - allaqachon bosganlar;
      - davomat kuzatilmaydigan rol (Boshliq);
      - Telegram'ga ulanmaganlar (`telegram_id is None`).

    TAKRORLANMASLIK: tick har daqiqada ishlaydi, ya'ni "N daqiqa qoldi" sharti
    bir necha marta rost bo'ladi. `AttendanceReminder` jadvalidagi
    UNIQUE(user_id, date, kind) yozuvi HAR NUQTA bir kunda bir marta
    yuborilishini kafolatlaydi (poyga holatida ham — ikkinchi tick
    IntegrityError oladi). `kind` = "check_in_10" / "check_out_0" ko'rinishida.

    BITTA TICK'DA BITTA NUQTA: tsikl birinchi mos kelgan nuqtada to'xtaydi.
    Aks holda cron uzoq to'xtab qolgach, xodimga uchala xabar ketma-ket
    kelib, "10 daqiqa qoldi" va "boshlandi" bir vaqtda tushardi.
    """
    # `_effective_today`/`_to_min` — ish oynasi qoidasining YAGONA manbai
    # (hourly_plan). Circular importdan qochish uchun funksiya ichida.
    from api.routers.hourly_plan import _effective_today, _to_min
    from api.services.attendance import is_excused_day

    # Nuqtalar KAMAYISH tartibida ("10,5,0"): pastdagi tsikl birinchi mos
    # kelganida to'xtaydi, ya'ni eng uzoq nuqta birinchi tekshirilishi kerak.
    offsets = sorted(
        {int(x) for x in settings.attendance_reminder_offsets_min.split(",") if x.strip()},
        reverse=True,
    )
    before_catchup = settings.attendance_reminder_catchup_min

    now_local = datetime.now(TASHKENT_TZ)
    day = today_local()
    now_min = now_local.hour * 60 + now_local.minute

    users = list(
        await db.scalars(
            select(User).where(
                User.role.in_(ATTENDANCE_TRACKED_ROLES),
                User.is_active.is_(True),
                User.telegram_id.isnot(None),
            )
        )
    )

    already = {
        (r.user_id, r.kind)
        for r in await db.scalars(select(AttendanceReminder).where(AttendanceReminder.date == day))
    }

    planned: list[dict] = []
    for user in users:
        is_working, start, end = await _effective_today(db, user, day)
        if not is_working:
            continue  # dam kuni — eslatma ham, kechikish ham yo'q
        if await is_excused_day(db, user.id, day):
            continue  # sababli kun — kelishi shart emas

        att = await db.scalar(
            select(Attendance).where(Attendance.user_id == user.id, Attendance.date == day)
        )

        # ── Kelish eslatmasi: 10 daq, 5 daq qolganda va AYNI VAQTIDA ──
        if start and (att is None or att.check_in_time is None):
            delta = _to_min(start) - now_min  # ish boshlanishigacha qolgan daqiqa
            for off in offsets:
                # `off - catchup <= delta <= off`: cron bir-ikki daqiqaga
                # kechiksa ham eslatma tushib qolmaydi. Yuqori chegara `off`
                # — aks holda 10 daqiqalik eslatma 12 daqiqa qolganda kelib,
                # matndagi "10 daqiqa" yolg'on bo'lardi.
                if off - before_catchup <= delta <= off and (user.id, f"check_in_{off}") not in already:
                    planned.append({"user": user, "kind": f"check_in_{off}", "at": start, "off": off})
                    break  # bitta tick'da bitta nuqta — ketma-ket yubormaymiz

        # ── Ketish eslatmasi: faqat «Keldim» bosgan, «Ketdim» bosmaganlarga ──
        # Umuman kelmagan odamga "ketishni unutmang" deyish ma'nosiz.
        if end and att is not None and att.check_in_time is not None and att.check_out_time is None:
            delta = _to_min(end) - now_min
            for off in offsets:
                # 0-nuqtada pastki chegara YO'Q: ish tugagach ham «Ketdim»
                # bosish mumkin va kerak (aks holda `worked_minutes` yozilmay
                # qoladi), shuning uchun kechikkan tick ham yuboraveradi.
                lo = None if off == 0 else off - before_catchup
                hit = delta <= off if lo is None else lo <= delta <= off
                if hit and (user.id, f"check_out_{off}") not in already:
                    planned.append({"user": user, "kind": f"check_out_{off}", "at": end, "off": off})
                    break

    if payload.dry_run:
        return {
            "dry_run": True,
            "planned": [
                {"user_id": p["user"].id, "full_name": p["user"].full_name, "kind": p["kind"], "at": p["at"]}
                for p in planned
            ],
        }

    sent = 0
    for p in planned:
        user, kind = p["user"], p["kind"]
        # Izni AVVAL yozamiz: yuborish sekin (Telegram+FCM) va shu orada
        # keyingi tick kelib qolsa, ikkalasi ham yuborib yuborardi.
        db.add(AttendanceReminder(user_id=user.id, date=day, kind=kind))
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            continue  # boshqa tick ulgurdi — bu yerda jim o'tamiz

        # Matn nuqtaga qarab farq qiladi: uchta bir xil xabar kelsa xodim
        # ularni o'qimay qo'yadi. 0-nuqtada "qoldi" emas, "boshlandi/tugadi".
        off, arriving = p["off"], kind.startswith("check_in")
        if off == 0:
            text = (
                f"🔔 Ish vaqti boshlandi ({p['at']}) — «Keldim» ni bosing."
                if arriving
                else f"🔔 Ish vaqti tugadi ({p['at']}) — «Ketdim» ni bosing."
            )
        else:
            text = (
                f"⏰ {off} daqiqadan keyin ish boshlanadi ({p['at']}) — «Keldim» bosishni unutmang."
                if arriving
                else f"⏰ {off} daqiqadan keyin ish tugaydi ({p['at']}) — «Ketdim» bosishni unutmang."
            )
        # UX2-W4 (C2/C7): xabar «bosing» deydi — bosadigan TUGMA ham bo'lsin;
        # force_telegram — bu eslatma jarimaga to'g'ridan-to'g'ri ta'sir qiladi,
        # push kanalida yo'qolib qolishi mumkin emas.
        btn_label = "✅ Keldim qilish" if arriving else "🚪 Ketdim qilish"
        res = await notify_user(
            db,
            user,
            Category.ATTENDANCE_REMINDER,
            text,
            reply_markup=inline_url_keyboard(
                [[(btn_label, f"{settings.frontend_url}/check-in")]]
            ),
            data={"path": "/check-in"},
            force_telegram=True,
        )
        if res["telegram"] or res["push"]:
            sent += 1

    return {"date": day.isoformat(), "candidates": len(planned), "sent": sent}


# ─────────────────────────────────────────────
# Tushuntirish xati (sababsiz kelmagan kun)
# ─────────────────────────────────────────────


class ExplanationAnswer(BaseModel):
    """Bot orqali xodimning javobi. Shaxs `telegram_id`dan yechiladi —
    mijoz `user_id` yubora olmaydi (boshqa birov nomidan javob yozmasin)."""

    telegram_id: int
    answer_text: str = Field(min_length=3, max_length=2000)


class ExplanationDecision(BaseModel):
    """HR qarori. `accept=True` — sababli deb qabul qilinadi va MAVJUD
    `ExcusedDay` mexanizmi orqali kun sababliga o'tadi (jarima o'z-o'zidan
    tushadi). `accept=False` — jarima o'z kuchida qoladi."""

    accept: bool
    note: str | None = Field(default=None, max_length=1000)


def _explanation_out(req: ExplanationRequest, full_name: str | None = None) -> dict:
    return {
        "id": req.id,
        "user_id": req.user_id,
        "user_full_name": full_name,
        "date": req.date.isoformat(),
        "status": req.status,
        "asked_at": req.asked_at.isoformat() if req.asked_at else None,
        "answer_text": req.answer_text,
        "answered_at": req.answered_at.isoformat() if req.answered_at else None,
        "decided_by": req.decided_by,
        "decided_at": req.decided_at.isoformat() if req.decided_at else None,
        "decision_note": req.decision_note,
    }


@router.post("/explanations/{req_id}/answer", dependencies=[Depends(verify_bot_secret)])
async def answer_explanation(
    req_id: int, payload: ExplanationAnswer, db: AsyncSession = Depends(get_db)
) -> dict:
    """Xodim botda tushuntirish yozadi."""
    req = await db.get(ExplanationRequest, req_id)
    if req is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "So'rov topilmadi")

    user = await db.scalar(select(User).where(User.telegram_id == payload.telegram_id))
    if user is None or user.id != req.user_id:
        # BOSHQA odamning so'roviga javob yozib bo'lmaydi — callback tugmasi
        # boshqa chatga forward qilinsa ham.
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Bu so'rov sizga tegishli emas")
    if req.status in (ExplanationStatus.accepted.value, ExplanationStatus.rejected.value):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Bu so'rov allaqachon hal qilingan")

    req.answer_text = payload.answer_text.strip()
    req.answered_at = datetime.utcnow()
    req.status = ExplanationStatus.answered.value
    await db.commit()

    hrs = list(
        await db.scalars(
            select(User).where(
                User.role.in_((Role.hr.value, Role.boss.value)), User.telegram_id.isnot(None)
            )
        )
    )
    text = (
        f"📄 <b>Tushuntirish xati keldi</b>\nXodim: {user.full_name}\n"
        f"Sana: {req.date}\nJavob: {json.dumps(req.answer_text, ensure_ascii=False)[1:-1]}"
    )
    for hr in hrs:
        await notify_user(db, hr, Category.APPROVALS, text, data={"path": "/excused-days"})

    return {"ok": True, "status": req.status}


@router.get("/explanations")
async def list_explanations(
    status_filter: str | None = None,
    _actor: User = Depends(require_roles(*ATTENDANCE_EDIT_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """HR/Boshliq uchun tushuntirish xatlari ro'yxati (yangi birinchi)."""
    q = select(ExplanationRequest).order_by(ExplanationRequest.date.desc(), ExplanationRequest.id.desc())
    if status_filter:
        q = q.where(ExplanationRequest.status == status_filter)
    rows = list(await db.scalars(q))
    names = {
        u.id: u.full_name
        for u in await db.scalars(select(User).where(User.id.in_({r.user_id for r in rows} or {0})))
    }
    return [_explanation_out(r, names.get(r.user_id)) for r in rows]


@router.post("/explanations/{req_id}/decide")
async def decide_explanation(
    req_id: int,
    payload: ExplanationDecision,
    actor: User = Depends(require_roles(*ATTENDANCE_EDIT_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """HR qarori.

    `accept=True` — MAVJUD `ExcusedDay` yaratiladi (darhol `approved`) va
    o'sha kungi davomat yozuvi qayta hisoblanadi: `is_excused_day` rost
    bo'lgach `recompute_attendance` kechikish/jarima holatini o'zi to'g'rilaydi.
    ⚠️ Yangi jarima yo'li YARATILMAYDI — aks holda ikkita mustaqil hisob
    paydo bo'lardi."""
    req = await db.get(ExplanationRequest, req_id)
    if req is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "So'rov topilmadi")

    target = await db.get(User, req.user_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Xodim topilmadi")

    req.status = (
        ExplanationStatus.accepted.value if payload.accept else ExplanationStatus.rejected.value
    )
    req.decided_by = actor.id
    req.decided_at = datetime.utcnow()
    req.decision_note = (payload.note or "").strip() or None

    if payload.accept:
        # Mavjud mexanizm: sababli kun. Dublikat bo'lmasligi uchun avval
        # tekshiriladi (xodim o'zi ham so'rov yuborgan bo'lishi mumkin).
        existing = await db.scalar(
            select(ExcusedDay).where(
                ExcusedDay.user_id == target.id,
                ExcusedDay.date == req.date,
                ExcusedDay.status.in_((ExcusedStatus.pending.value, ExcusedStatus.approved.value)),
            )
        )
        if existing is None:
            db.add(
                ExcusedDay(
                    user_id=target.id,
                    date=req.date,
                    reason=req.answer_text or "Tushuntirish xati qabul qilindi",
                    status=ExcusedStatus.approved.value,
                    decided_by=actor.id,
                    decided_at=datetime.utcnow(),
                )
            )
        elif existing.status != ExcusedStatus.approved.value:
            existing.status = ExcusedStatus.approved.value
            existing.decided_by = actor.id
            existing.decided_at = datetime.utcnow()
        await db.flush()

        # O'sha kungi davomat yozuvini qayta hisoblash — `is_excused_day` endi
        # rost, ya'ni kechikish/status o'z-o'zidan to'g'rilanadi.
        att = await db.scalar(
            select(Attendance).where(Attendance.user_id == target.id, Attendance.date == req.date)
        )
        if att is not None:
            await recompute_attendance(db, att, target)

    db.add(
        AuditLog(
            actor_id=actor.id,
            action="explanation_decided",
            target_user_id=target.id,
            before={"status": ExplanationStatus.answered.value},
            after={"date": req.date.isoformat(), "accepted": payload.accept, "note": req.decision_note},
        )
    )
    await db.commit()
    await db.refresh(req)

    if target.telegram_id:
        verdict = (
            "✅ Tushuntirishingiz qabul qilindi — kun sababli deb belgilandi."
            if payload.accept
            else "❌ Tushuntirishingiz qabul qilinmadi — kun sababsiz bo'lib qoladi."
        )
        await notify_user(db, target, Category.DECISIONS, f"{verdict}\nSana: {req.date}")

    return _explanation_out(req, target.full_name)
