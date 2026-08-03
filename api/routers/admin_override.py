"""Dasturchi rejimi (super-admin) — cheklovsiz boshqaruv qatlami.

Spetsifikatsiya: OYLIK_JARIMA_REJASI.md 11-bo'lim. Barcha endpointlar
`Depends(require_dasturchi)` — FAQAT Dasturchi. Tamoyillar (11.2-band):
1. Yagona darvoza — `api/deps.py::is_superadmin` (bu yerda emas, chaqiruvchi
   matritsalarda ishlatiladi: norms.py, tasks.py).
2. Har bir override — majburiy sabab (`override_reason`, min 5 belgi).
3. Yumshoq o'chirish sukut bo'yicha (`Norm`, `SalaryRate`); qattiq o'chirish
   faqat `hard=true` bilan.
4. Cheklovsizlik ≠ izsizlik — har amal `AuditLog(action="override_*")` ga
   yoziladi, Boshliq buni `/admin/audit/overrides` orqali ko'ra oladi.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete as sa_delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_db, require_dasturchi
from api.schemas import (
    AdminAttendanceEditorGrant,
    AdminAttendanceManualUpdate,
    AdminForceRole,
    AdminNormSet,
    AdminOverrideReason,
    AdminRecordPatch,
)
from api.services.payroll import PayrollLocked, run_payroll
from api.timeutil import today_local
from db.models import (
    Attendance,
    AuditLog,
    Bonus,
    DailyResult,
    ExcusedDay,
    FinePolicy,
    MobilografVideo,
    Norm,
    OvertimeEntry,
    PayrollAdjustment,
    PayrollPeriod,
    Payslip,
    PayslipItem,
    Role,
    SalaryRate,
    TaskModel,
    User,
)

router = APIRouter(prefix="/admin", tags=["admin-override"])


def _json_safe(value):
    """`date`/`datetime` -> ISO satr, `Decimal` -> `float`. Bu qiymatlar HTTP
    javobida FastAPI'ning `jsonable_encoder`i orqali baribir to'g'ri chiqadi,
    lekin `_row_to_dict()` natijasi `AuditLog.before/after` (JSON ustun)ga
    HAM yoziladi — u yerda SQLAlchemy oddiy `json.dumps` ishlatadi va
    `date`/`Decimal`ni tushunmay 500 beradi. Shu sabab bu yerda oldindan
    xavfsiz turga o'giriladi."""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def _row_to_dict(row) -> dict:
    """Har qanday ORM qatorini JSON-xavfsiz dict'ga — ustunlar ro'yxati
    orqali (HTTP javobi va `AuditLog` uchun bir xil, ikkalasida ham ishlaydi)."""
    return {c.name: _json_safe(getattr(row, c.name)) for c in row.__table__.columns}


async def _log_override(
    db: AsyncSession, actor: User, action: str, target_user_id: int | None, before, after, reason: str
) -> None:
    db.add(
        AuditLog(
            actor_id=actor.id,
            action=f"override_{action}",
            target_user_id=target_user_id,
            before=before,
            after={**(after or {}), "override_reason": reason},
        )
    )


# ─────────────────────────────────────────────
# Normalar — asosiy talab (11.3-band)
# ─────────────────────────────────────────────


@router.put("/norms/{user_id}/{metric}")
async def admin_set_norm(
    user_id: int,
    metric: str,
    payload: AdminNormSet,
    actor: User = Depends(require_dasturchi),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """HAR QANDAY qiymat, metrika/lavozim cheklovisiz, HAR QANDAY rolga
    (hr/rop/boss ham) — oddiy `POST /norms` matritsasidan farqli, bu yerda
    hech qanday tekshiruv yo'q, faqat xodim mavjudligi."""
    target = await db.get(User, user_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Foydalanuvchi topilmadi")

    norm = Norm(
        user_id=user_id, metric_type=metric, value=payload.value,
        changed_by=actor.id, effective_from=today_local(),
    )
    db.add(norm)
    await _log_override(
        db, actor, "norm_set", user_id, None,
        {"metric": metric, "value": payload.value}, payload.override_reason,
    )
    await db.commit()
    await db.refresh(norm)
    return _row_to_dict(norm)


@router.delete("/norms/{norm_id}")
async def admin_delete_norm(
    norm_id: int,
    payload: AdminOverrideReason,
    hard: bool = Query(default=False),
    actor: User = Depends(require_dasturchi),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Bitta tarix yozuvini o'chiradi — sukut bo'yicha YUMSHOQ (keyin
    `restore` bilan tiklanadi), `hard=true` bilan butunlay."""
    norm = await db.get(Norm, norm_id)
    if norm is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Norma yozuvi topilmadi")
    before = _row_to_dict(norm)
    if hard:
        await db.delete(norm)
    else:
        norm.deleted_at = datetime.utcnow()
        norm.deleted_by = actor.id
        norm.deleted_reason = payload.override_reason
    await _log_override(
        db, actor, "norm_deleted" if not hard else "norm_hard_deleted",
        norm.user_id, before, {"hard": hard}, payload.override_reason,
    )
    await db.commit()
    return {"deleted": True, "hard": hard}


@router.delete("/norms/{user_id}/{metric}")
async def admin_clear_metric(
    user_id: int,
    metric: str,
    payload: AdminOverrideReason,
    actor: User = Depends(require_dasturchi),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Metrikani BUTUNLAY tozalaydi — shu xodim+metrika bo'yicha barcha
    FAOL (o'chirilmagan) tarix qatorlarini yumshoq o'chiradi."""
    rows = list(
        await db.scalars(
            select(Norm).where(
                Norm.user_id == user_id, Norm.metric_type == metric, Norm.deleted_at.is_(None)
            )
        )
    )
    now = datetime.utcnow()
    for n in rows:
        n.deleted_at = now
        n.deleted_by = actor.id
        n.deleted_reason = payload.override_reason
    await _log_override(
        db, actor, "norm_metric_cleared", user_id, None,
        {"metric": metric, "cleared_count": len(rows)}, payload.override_reason,
    )
    await db.commit()
    return {"cleared": len(rows)}


@router.post("/norms/{user_id}/revert")
async def admin_revert_norm(
    user_id: int,
    metric: str,
    payload: AdminOverrideReason,
    actor: User = Depends(require_dasturchi),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Amaldagi (eng so'nggi FAOL) qiymatni yumshoq o'chirib, undan OLDINGI
    qiymatga "qaytaradi" (u avtomatik amaldagi bo'lib qoladi — `_current_value`
    eng so'nggi FAOL qatorni oladi)."""
    latest = await db.scalar(
        select(Norm)
        .where(Norm.user_id == user_id, Norm.metric_type == metric, Norm.deleted_at.is_(None))
        .order_by(Norm.effective_from.desc(), Norm.created_at.desc())
        .limit(1)
    )
    if latest is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bu xodim/metrika uchun faol norma topilmadi")
    latest.deleted_at = datetime.utcnow()
    latest.deleted_by = actor.id
    latest.deleted_reason = payload.override_reason

    previous = await db.scalar(
        select(Norm)
        .where(
            Norm.user_id == user_id, Norm.metric_type == metric, Norm.deleted_at.is_(None), Norm.id != latest.id
        )
        .order_by(Norm.effective_from.desc(), Norm.created_at.desc())
        .limit(1)
    )
    await _log_override(
        db, actor, "norm_reverted", user_id,
        {"value": latest.value}, {"reverted_to": previous.value if previous else None}, payload.override_reason,
    )
    await db.commit()
    return {"reverted": True, "current_value": previous.value if previous else None}


# ─────────────────────────────────────────────
# Universal yozuv boshqaruvi
# ─────────────────────────────────────────────

# entity -> (Model, PATCH uchun oq ro'yxat, yumshoq o'chirish qo'llab-quvvatlanadimi)
ENTITY_REGISTRY: dict[str, tuple[type, set[str], bool]] = {
    "norm": (Norm, {"value", "metric_type", "effective_from"}, True),
    "attendance": (Attendance, {"status", "note", "late_minutes", "early_leave_minutes", "worked_minutes"}, False),
    "excused_day": (ExcusedDay, {"reason", "status"}, False),
    "task": (TaskModel, {"title", "description", "deadline", "status"}, False),
    "daily_result": (DailyResult, {"conversations_count", "visits_count"}, False),
    "mobilograf_video": (MobilografVideo, {"status", "video_type"}, False),
    "overtime": (OvertimeEntry, {"minutes", "status", "note"}, False),
    # `effective_from` YO'Q — UNIQUE(user_id, effective_from) o'chirilganlarni
    # ham hisobga oladi, sanani PATCH orqali o'zgartirish dublikat xatosiga
    # olib kelishi mumkin. Sanani o'zgartirish kerak bo'lsa — o'chirib (soft)
    # yangisini `/payroll/rates` orqali yaratish.
    "salary_rate": (SalaryRate, {"amount", "pay_basis", "note"}, True),
    "payroll_adjustment": (PayrollAdjustment, {"amount", "kind", "reason"}, False),
    "fine_policy": (
        FinePolicy,
        {
            "free_late_minutes_per_month", "fine_mode", "fine_per_day", "absent_mode", "absent_fine",
            "monthly_cap_percent", "monthly_cap_amount", "fine_applies_to", "is_active", "grace_minutes",
        },
        False,
    ),
    "bonus": (Bonus, {"amount"}, False),
}

# Har entity uchun "target_user_id" ustuni nomi (audit uchun) — hammasi
# to'g'ridan-to'g'ri user_id, faqat norm/salary_rate/fine_policy farqli emas
# (fine_policy'da scope_id polimorfik, shuning uchun None qoldiriladi).
_USER_FIELD = {
    "norm": "user_id", "attendance": "user_id", "excused_day": "user_id", "task": "assigned_to",
    "daily_result": "user_id", "mobilograf_video": "user_id", "overtime": "user_id",
    "salary_rate": "user_id", "payroll_adjustment": "user_id", "bonus": "user_id",
}


def _target_user_id(entity: str, row) -> int | None:
    field = _USER_FIELD.get(entity)
    return getattr(row, field, None) if field else None


def _resolve_entity(entity: str) -> tuple[type, set[str], bool]:
    if entity not in ENTITY_REGISTRY:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, f"Noma'lum entity: {entity}. Mavjud: {', '.join(ENTITY_REGISTRY)}"
        )
    return ENTITY_REGISTRY[entity]


@router.get("/records/{entity}")
async def list_records(
    entity: str,
    include_deleted: bool = Query(default=True),
    limit: int = Query(default=200, le=1000),
    _actor: User = Depends(require_dasturchi),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    model, _fields, soft = _resolve_entity(entity)
    q = select(model)
    if soft and not include_deleted:
        q = q.where(model.deleted_at.is_(None))
    q = q.order_by(model.id.desc()).limit(limit)
    rows = list(await db.scalars(q))
    return [_row_to_dict(r) for r in rows]


@router.patch("/records/{entity}/{record_id}")
async def patch_record(
    entity: str,
    record_id: int,
    payload: AdminRecordPatch,
    actor: User = Depends(require_dasturchi),
    db: AsyncSession = Depends(get_db),
) -> dict:
    model, allowed_fields, _soft = _resolve_entity(entity)
    row = await db.get(model, record_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Yozuv topilmadi")

    unknown = set(payload.fields) - allowed_fields
    if unknown:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Bu maydonlar '{entity}' uchun tahrirlanmaydi: {', '.join(sorted(unknown))}. "
            f"Ruxsat etilgan: {', '.join(sorted(allowed_fields))}",
        )
    if not payload.fields:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Hech qanday maydon berilmagan")

    before = _row_to_dict(row)
    for field, value in payload.fields.items():
        setattr(row, field, value)

    target_user_id = _target_user_id(entity, row)
    await _log_override(
        db, actor, f"record_patched:{entity}", target_user_id, before, payload.fields, payload.override_reason
    )
    await db.commit()
    await db.refresh(row)
    return _row_to_dict(row)


@router.delete("/records/{entity}/{record_id}")
async def delete_record(
    entity: str,
    record_id: int,
    payload: AdminOverrideReason,
    hard: bool = Query(default=False),
    actor: User = Depends(require_dasturchi),
    db: AsyncSession = Depends(get_db),
) -> dict:
    model, _fields, soft = _resolve_entity(entity)
    row = await db.get(model, record_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Yozuv topilmadi")

    before = _row_to_dict(row)
    target_user_id = _target_user_id(entity, row)

    actually_hard = hard or not soft
    if actually_hard:
        await db.delete(row)
    else:
        row.deleted_at = datetime.utcnow()
        row.deleted_by = actor.id
        row.deleted_reason = payload.override_reason

    await _log_override(
        db, actor, f"record_deleted:{entity}", target_user_id,
        before, {"hard": actually_hard}, payload.override_reason,
    )
    await db.commit()
    return {"deleted": True, "hard": actually_hard}


@router.post("/records/{entity}/{record_id}/restore")
async def restore_record(
    entity: str,
    record_id: int,
    payload: AdminOverrideReason,
    actor: User = Depends(require_dasturchi),
    db: AsyncSession = Depends(get_db),
) -> dict:
    model, _fields, soft = _resolve_entity(entity)
    if not soft:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"'{entity}' yumshoq o'chirishni qo'llab-quvvatlamaydi")
    row = await db.get(model, record_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Yozuv topilmadi")
    if row.deleted_at is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Bu yozuv o'chirilmagan")

    target_user_id = _target_user_id(entity, row)
    row.deleted_at = None
    row.deleted_by = None
    row.deleted_reason = None
    await _log_override(db, actor, f"record_restored:{entity}", target_user_id, None, None, payload.override_reason)
    await db.commit()
    return {"restored": True}


# ─────────────────────────────────────────────
# Payroll qulflari
# ─────────────────────────────────────────────


@router.post("/payroll/{period}/unlock")
async def unlock_period(
    period: str, payload: AdminOverrideReason, actor: User = Depends(require_dasturchi), db: AsyncSession = Depends(get_db)
) -> dict:
    period_row = await db.scalar(select(PayrollPeriod).where(PayrollPeriod.period == period))
    if period_row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Davr topilmadi")
    was_locked = period_row.locked
    period_row.locked = False
    await _log_override(
        db, actor, "payroll_period_unlocked", None, {"locked": was_locked}, {"locked": False}, payload.override_reason
    )
    await db.commit()
    return {"period": period, "locked": False}


@router.post("/payroll/{period}/force-recalculate")
async def force_recalculate(
    period: str, payload: AdminOverrideReason, actor: User = Depends(require_dasturchi), db: AsyncSession = Depends(get_db)
) -> dict:
    """Qulfni avtomatik ochib, qayta hisoblaydi — bitta amalda (2 bosqichli
    unlock+calculate o'rniga qulaylik uchun)."""
    period_row = await db.scalar(select(PayrollPeriod).where(PayrollPeriod.period == period))
    if period_row is not None and period_row.locked:
        period_row.locked = False
        await _log_override(
            db, actor, "payroll_period_force_unlocked", None, {"locked": True}, {"locked": False},
            payload.override_reason,
        )
        await db.commit()
    try:
        result = await run_payroll(db, period)
    except PayrollLocked as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    await _log_override(db, actor, "payroll_force_recalculated", None, None, result, payload.override_reason)
    await db.commit()
    return result


@router.patch("/payroll/{period}/user/{user_id}")
async def patch_payslip(
    period: str,
    user_id: int,
    payload: AdminRecordPatch,
    actor: User = Depends(require_dasturchi),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Tasdiqlangan/hisoblangan varaqaning summasini QO'LDA tuzatadi —
    keyingi `calculate` bu yozuvni ustidan yozib yuboradi, shuning uchun
    faqat davr QULFLANGANDAN keyin (yakuniy holatda) ishlatilishi kerak."""
    allowed = {
        "base_amount", "fine_amount", "absent_deduction", "overtime_amount",
        "bonus_amount", "adjustments_plus", "adjustments_minus", "gross", "net", "status",
    }
    unknown = set(payload.fields) - allowed
    if unknown:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Bu maydonlar tahrirlanmaydi: {', '.join(unknown)}")

    payslip = await db.scalar(select(Payslip).where(Payslip.user_id == user_id, Payslip.period == period))
    if payslip is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payslip topilmadi")

    before = _row_to_dict(payslip)
    for field, value in payload.fields.items():
        setattr(payslip, field, value)
    await _log_override(
        db, actor, "payslip_patched", user_id, before, payload.fields, payload.override_reason
    )
    await db.commit()
    await db.refresh(payslip)
    return _row_to_dict(payslip)


@router.delete("/payroll/{period}")
async def delete_period(
    period: str, payload: AdminOverrideReason, actor: User = Depends(require_dasturchi), db: AsyncSession = Depends(get_db)
) -> dict:
    """Butun oy hisobini BEKOR QILADI — barcha payslip/item + davrning o'zi
    o'chiriladi (qattiq, bu yerda "yumshoq" versiyasi yo'q — davr butunlay
    qayta hisoblanishi mo'ljallangan)."""
    payslips = list(await db.scalars(select(Payslip).where(Payslip.period == period)))
    for p in payslips:
        await db.execute(sa_delete(PayslipItem).where(PayslipItem.payslip_id == p.id))
        await db.delete(p)
    period_row = await db.scalar(select(PayrollPeriod).where(PayrollPeriod.period == period))
    if period_row is not None:
        await db.delete(period_row)

    await _log_override(
        db, actor, "payroll_period_deleted", None, None, {"period": period, "payslip_count": len(payslips)},
        payload.override_reason,
    )
    await db.commit()
    return {"deleted_payslips": len(payslips)}


# ─────────────────────────────────────────────
# Tizim darajasi
# ─────────────────────────────────────────────


@router.post("/attendance/recalculate")
async def recalculate_attendance(
    date_from: date,
    date_to: date,
    payload: AdminOverrideReason,
    actor: User = Depends(require_dasturchi),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Berilgan sana oralig'idagi barcha Attendance yozuvlarini (check-in
    bo'lganlarini) joriy ish jadvali/grace qoidasiga qarab QAYTA hisoblaydi —
    masalan `attendance_grace_minutes` sozlamasi o'zgargandan keyin."""
    from api.services.attendance import recompute_attendance

    rows = list(
        await db.scalars(
            select(Attendance).where(
                Attendance.date >= date_from, Attendance.date <= date_to, Attendance.check_in_time.isnot(None)
            )
        )
    )
    recalculated = 0
    for att in rows:
        user = await db.get(User, att.user_id)
        if user is None:
            continue
        await recompute_attendance(db, att, user)
        recalculated += 1

    await _log_override(
        db, actor, "attendance_recalculated", None, None,
        {"date_from": date_from.isoformat(), "date_to": date_to.isoformat(), "count": recalculated},
        payload.override_reason,
    )
    await db.commit()
    return {"recalculated": recalculated}


@router.put("/attendance/manual")
async def admin_manual_attendance(
    payload: AdminAttendanceManualUpdate,
    _: User = Depends(require_dasturchi),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Davomat keldi/ketdi vaqtini QO'LDA tuzatadi — **AUDITSIZ va JIM**.

    ⚠️ Bu endpoint shu modulning 4-tamoyilidan (11.2-band, "Cheklovsizlik ≠
    izsizlik") ATAYLAB chetga chiqadi: egasining aniq talabi — Dasturchi
    tuzatishi "auditlarga tushmasdan" bo'lsin. Shuning uchun bu yerda
    `_log_override` chaqirilmaydi va hech qanday `AuditLog` yozilmaydi.
    Bot xabari ham yuborilmaydi (davomat tahririda umuman bot xabari yo'q —
    faqat shu holat saqlanadi).

    Oqibati ochiq aytilgan: bu vaqtni kim/qachon o'zgartirgani keyinchalik
    HECH QAYERDAN bilib bo'lmaydi. Davomat oylik va kechikish jarimasini
    belgilagani uchun, nizo chiqsa tiklab bo'lmaydi.

    Audit KERAK bo'lgan variant — `PUT /attendance/manual` (HR/Boshliq va
    shaxsan ruxsat berilgan odamlar; ular uchun audit saytda ko'rinadi).

    Xuddi `/attendance/manual` kabi yozuvni YARATADI ham — xodim «Keldim»
    bosishni unutgan kun uchun yangi yozuv ochiladi."""
    from api.routers.attendance import apply_manual_attendance

    target = await db.get(User, payload.user_id)
    if target is None or not target.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Xodim topilmadi")

    att, _before, created = await apply_manual_attendance(db, payload, target)
    await db.commit()
    await db.refresh(att)
    return {
        "id": att.id,
        "user_id": att.user_id,
        "date": att.date.isoformat(),
        "check_in_time": att.check_in_time.isoformat() if att.check_in_time else None,
        "check_out_time": att.check_out_time.isoformat() if att.check_out_time else None,
        "late_minutes": att.late_minutes,
        "worked_minutes": att.worked_minutes,
        "status": att.status,
        "created": created,
        "audited": False,
    }


@router.get("/attendance-editors")
async def list_attendance_editors(
    _: User = Depends(require_dasturchi), db: AsyncSession = Depends(get_db)
) -> list[dict]:
    """Davomat vaqtini tuzatish huquqi SHAXSAN berilgan odamlar ro'yxati.
    Roli bo'yicha huquqi borlar (hr/boss/dasturchi) bu ro'yxatga kirmaydi —
    ularga bayroq kerak emas."""
    rows = list(
        await db.scalars(
            select(User).where(User.can_edit_attendance.is_(True)).order_by(User.full_name)
        )
    )
    return [{"id": u.id, "full_name": u.full_name, "role": u.role, "is_active": u.is_active} for u in rows]


@router.post("/users/{user_id}/attendance-editor")
async def set_attendance_editor(
    user_id: int,
    payload: AdminAttendanceEditorGrant,
    actor: User = Depends(require_dasturchi),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Davomat vaqtini tuzatish huquqini beradi/olib qo'yadi (faqat Dasturchi).

    DIQQAT — bu amalning O'ZI audit jurnaliga YOZILADI (tuzatishlardan
    farqli). Sabab: bu vaqt tuzatish emas, HUQUQ berish; kimga qachon
    berilgani bilinmasa, keyinchalik "bu odam nega tahrirlay olyapti?"
    degan savolga javob qolmaydi. Egasi jim bo'lishini so'ragan narsa —
    vaqt tuzatishning o'zi edi."""
    target = await db.get(User, user_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Foydalanuvchi topilmadi")

    before = bool(target.can_edit_attendance)
    target.can_edit_attendance = payload.granted
    await _log_override(
        db, actor, "attendance_editor_set", user_id,
        {"can_edit_attendance": before}, {"can_edit_attendance": payload.granted},
        payload.override_reason,
    )
    await db.commit()
    return {"user_id": user_id, "can_edit_attendance": payload.granted}


@router.post("/users/{user_id}/force-role")
async def force_role(
    user_id: int, payload: AdminForceRole, actor: User = Depends(require_dasturchi), db: AsyncSession = Depends(get_db)
) -> dict:
    target = await db.get(User, user_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Foydalanuvchi topilmadi")
    valid_roles = {r.value for r in Role}
    if payload.role not in valid_roles:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Noto'g'ri rol: {payload.role}")

    before_role = target.role
    target.role = payload.role
    await _log_override(
        db, actor, "user_role_forced", user_id, {"role": before_role}, {"role": payload.role}, payload.override_reason
    )
    await db.commit()

    # Dasturchi O'ZINI o'zgartirsa — Boshliqqa darhol xabar (11.6-band).
    if target.id == actor.id:
        bosses = list(
            await db.scalars(select(User).where(User.role == Role.boss.value, User.telegram_id.isnot(None)))
        )
        from api.telegram_notify import send_message

        for b in bosses:
            await send_message(
                b.telegram_id,
                f"⚠️ Dasturchi {actor.full_name} o'z rolini {before_role} → {payload.role} ga o'zgartirdi.",
            )
    return {"user_id": user_id, "role": payload.role}


@router.get("/audit/overrides")
async def list_override_audit(
    limit: int = Query(default=200, le=1000),
    _actor: User = Depends(require_dasturchi),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Faqat `override_*` amallar tarixi — Boshliq ham shu endpointdan
    (Dasturchi bo'lmasa 403) ko'ra olishi rejalashtirilgan (Bosqich 4, web);
    hozircha faqat Dasturchi (`require_dasturchi`)."""
    rows = list(
        await db.scalars(
            select(AuditLog)
            .where(AuditLog.action.like("override_%"))
            .order_by(AuditLog.id.desc())
            .limit(limit)
        )
    )
    return [_row_to_dict(r) for r in rows]
