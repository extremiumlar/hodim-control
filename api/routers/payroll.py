"""Payroll (oylik ish haqi + kechikish jarimasi + qo'shimcha ish) — API.

Hisoblash mantiqi `api/services/payroll.py`da (Bosqich 2); bu yerda faqat
HTTP qatlami: ruxsat matritsasi, validatsiya, audit, bot bildirishnomalari.
Spetsifikatsiya — OYLIK_JARIMA_REJASI.md 4-bo'lim.

Ruxsat ikki daraja (9-bo'lim, savol 8, QAROR):
- `PAYROLL_MANAGE_ROLES` (hr/boss/dasturchi) — sozlamalar, hisoblash,
  tasdiqlash, qo'lda qo'shimcha/ushlanma. ROP'da bu huquq YO'Q.
- `PAYROLL_VIEW_ROLES` (hr/rop/boss/dasturchi) — payslip'larni ko'rish, lekin
  ROP FAQAT o'z jamoasi uchun (`can_view_payroll`, `norms.py::can_manage_norms`
  bilan bir xil qamrov naqshi).

`reopen` (qulflangan davrni ochish) ATAYLAB shu routerda YO'Q — Bosqich 3.5
(Dasturchi rejimi, `admin_override.py`) ga tegishli."""
from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user, get_db, require_roles, verify_bot_secret
from api.schemas import (
    BotLateStatusOut,
    BotPayslipOut,
    FinePolicyIn,
    FinePolicyOut,
    OvertimeEntryDecide,
    OvertimeEntryIn,
    OvertimeEntryOut,
    OvertimeProfileIn,
    OvertimeProfileOut,
    PayrollAdjustmentIn,
    PayrollAdjustmentOut,
    PayrollCalculateRequest,
    PayrollPeriodOut,
    PayrollPreflightOut,
    PayslipDetailOut,
    PayslipItemOut,
    PayslipRow,
    ReadinessIssue,
    SalaryRateIn,
    SalaryRateOut,
)
from api.services.attendance import collect_readiness
from api.services.export import build_payroll_xlsx
from api.services.payroll import (
    PAYROLL_TRACKED_ROLES,
    PayrollLocked,
    _period_bounds,
    collect_attendance,
    compute_late_fine,
    detect_overtime_candidates,
    late_limit_event_for,
    previous_period,
    resolve_policy,
    run_payroll,
)
from api.telegram_notify import send_message
from api.timeutil import today_local
from db.models import (
    AuditLog,
    FinePolicy,
    OvertimeEntry,
    OvertimeEntryStatus,
    OvertimeProfile,
    PayrollAdjustment,
    PayrollPeriod,
    Payslip,
    PayslipItem,
    Position,
    Role,
    SalaryRate,
    User,
)

router = APIRouter(prefix="/payroll", tags=["payroll"])

PAYROLL_MANAGE_ROLES = (Role.hr.value, Role.boss.value, Role.dasturchi.value)
PAYROLL_VIEW_ROLES = (Role.hr.value, Role.rop.value, Role.boss.value, Role.dasturchi.value)


def can_view_payroll(actor: User, target: User) -> bool:
    """ROP faqat o'z jamoasini (bevosita `manager_id` yoki lavozimi "ROP
    boshqaradi" deb belgilangan) va o'zini ko'radi — boshqa rahbarlarning
    payslip'ini emas. HR/Boshliq/Dasturchi — hammani (`norms.py::
    can_manage_norms` bilan bir xil qamrov mantiqi, lekin faqat KO'RISH
    uchun — tahrir/tasdiqlash huquqi bermaydi)."""
    if actor.role in (Role.hr.value, Role.boss.value, Role.dasturchi.value):
        return True
    if actor.role == Role.rop.value:
        if target.id == actor.id:
            return True
        if target.role != Role.employee.value:
            return False
        if target.manager_id == actor.id:
            return True
        position = target.position
        return bool(position and position.managed_by_roles and Role.rop.value in position.managed_by_roles)
    return target.id == actor.id


def _require_view(actor: User = Depends(require_roles(*PAYROLL_VIEW_ROLES))) -> User:
    return actor


def _require_manage(actor: User = Depends(require_roles(*PAYROLL_MANAGE_ROLES))) -> User:
    return actor


async def _visible_users(db: AsyncSession, actor: User) -> list[User]:
    """Rahbar ko'ra oladigan davomat-kuzatiladigan xodimlar ro'yxati. ROP uchun
    `can_view_payroll` bilan filtrlanadi; boshqa rahbarlarga hammasi."""
    users = list(
        await db.scalars(
            select(User)
            .where(User.role.in_(PAYROLL_TRACKED_ROLES), User.is_active.is_(True))
            .order_by(User.full_name)
        )
    )
    if actor.role != Role.rop.value:
        return users
    return [u for u in users if can_view_payroll(actor, u)]


# ─────────────────────────────────────────────
# Sozlamalar — faqat HR/Boshliq/Dasturchi
# ─────────────────────────────────────────────


async def _policy_label(db: AsyncSession, policy: FinePolicy) -> str | None:
    if policy.scope == "user" and policy.scope_id:
        u = await db.get(User, policy.scope_id)
        return u.full_name if u else f"#{policy.scope_id}"
    if policy.scope == "position" and policy.scope_id:
        pos = await db.get(Position, policy.scope_id)
        return pos.name if pos else f"#{policy.scope_id}"
    return None


@router.get("/policies", response_model=list[FinePolicyOut])
async def list_policies(_actor: User = Depends(_require_manage), db: AsyncSession = Depends(get_db)):
    policies = list(await db.scalars(select(FinePolicy).order_by(FinePolicy.scope, FinePolicy.scope_id)))
    out: list[FinePolicyOut] = []
    for p in policies:
        row = FinePolicyOut.model_validate(p)
        row.scope_label = await _policy_label(db, p)
        out.append(row)
    return out


@router.put("/policies", response_model=FinePolicyOut)
async def upsert_policy(
    payload: FinePolicyIn, actor: User = Depends(_require_manage), db: AsyncSession = Depends(get_db)
):
    """Scope+scope_id bo'yicha upsert — mavjud bo'lsa yangilanadi, bo'lmasa
    yaratiladi. Har o'zgarish (jarima summasi/qoidasi — bevosita xodim
    haqiga ta'sir qiladi) auditga to'liq oldingi holat bilan yoziladi."""
    q = select(FinePolicy).where(FinePolicy.scope == payload.scope)
    q = q.where(FinePolicy.scope_id.is_(None)) if payload.scope_id is None else q.where(
        FinePolicy.scope_id == payload.scope_id
    )
    existing = await db.scalar(q)

    before = None
    if existing is not None:
        before = {c.name: getattr(existing, c.name) for c in FinePolicy.__table__.columns if c.name != "id"}
        for field, value in payload.model_dump(exclude={"scope", "scope_id"}).items():
            setattr(existing, field, value)
        policy = existing
    else:
        policy = FinePolicy(**payload.model_dump(), updated_by=actor.id)
        db.add(policy)
    policy.updated_by = actor.id

    db.add(
        AuditLog(
            actor_id=actor.id,
            action="fine_policy_upserted",
            target_user_id=payload.scope_id if payload.scope == "user" else None,
            before=before,
            after={"scope": payload.scope, "scope_id": payload.scope_id, **payload.model_dump()},
        )
    )
    await db.commit()
    await db.refresh(policy)
    row = FinePolicyOut.model_validate(policy)
    row.scope_label = await _policy_label(db, policy)
    return row


@router.delete("/policies/{policy_id}")
async def delete_policy(
    policy_id: int, actor: User = Depends(_require_manage), db: AsyncSession = Depends(get_db)
) -> dict:
    policy = await db.get(FinePolicy, policy_id)
    if policy is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Qoida topilmadi")
    db.add(
        AuditLog(
            actor_id=actor.id,
            action="fine_policy_deleted",
            target_user_id=policy.scope_id if policy.scope == "user" else None,
            before={"scope": policy.scope, "scope_id": policy.scope_id},
            after=None,
        )
    )
    await db.delete(policy)
    await db.commit()
    return {"deleted": True}


@router.get("/rates", response_model=list[SalaryRateOut])
async def list_rates(
    user_id: int, _actor: User = Depends(_require_manage), db: AsyncSession = Depends(get_db)
) -> list[SalaryRate]:
    # Yumshoq o'chirilgan (Bosqich 3.5) yozuvlar bu yerda ko'rinmaydi — ularni
    # ko'rish/tiklash faqat `/admin/records/salary_rate` orqali (Dasturchi).
    return list(
        await db.scalars(
            select(SalaryRate)
            .where(SalaryRate.user_id == user_id, SalaryRate.deleted_at.is_(None))
            .order_by(SalaryRate.effective_from.desc())
        )
    )


@router.post("/rates", response_model=SalaryRateOut)
async def create_rate(
    payload: SalaryRateIn, actor: User = Depends(_require_manage), db: AsyncSession = Depends(get_db)
) -> SalaryRate:
    target = await db.get(User, payload.user_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Xodim topilmadi")
    # UNIQUE(user_id, effective_from) YUMSHOQ o'chirilganlarni ham hisobga
    # oladi (baza darajasida) — shuning uchun bu yerdagi tekshiruv ham xuddi
    # shunday, `deleted_at`dan qat'i nazar. Xato sanani tuzatish uchun
    # `/admin/records/salary_rate/{id}` orqali TAHRIRLASH kerak, o'chirib
    # qayta yaratish EMAS (aks holda baza UNIQUE xatosi beradi).
    existing = await db.scalar(
        select(SalaryRate).where(
            SalaryRate.user_id == payload.user_id, SalaryRate.effective_from == payload.effective_from
        )
    )
    if existing is not None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Bu sanaga allaqachon stavka kiritilgan — avval eskisini o'zgartiring",
        )
    rate = SalaryRate(
        user_id=payload.user_id,
        amount=payload.amount,
        pay_basis=payload.pay_basis,
        effective_from=payload.effective_from,
        note=payload.note,
        changed_by=actor.id,
    )
    db.add(rate)
    db.add(
        AuditLog(
            actor_id=actor.id,
            action="salary_rate_created",
            target_user_id=payload.user_id,
            before=None,
            after={
                "amount": payload.amount,
                "pay_basis": payload.pay_basis,
                "effective_from": payload.effective_from.isoformat(),
            },
        )
    )
    await db.commit()
    await db.refresh(rate)
    return rate


@router.get("/overtime-profiles", response_model=list[OvertimeProfileOut])
async def list_overtime_profiles(
    _actor: User = Depends(_require_manage), db: AsyncSession = Depends(get_db)
) -> list[OvertimeProfileOut]:
    result = await db.execute(
        select(OvertimeProfile, User.full_name).join(User, OvertimeProfile.user_id == User.id)
    )
    out = []
    for profile, full_name in result.all():
        row = OvertimeProfileOut.model_validate(profile, from_attributes=True)
        row.user_full_name = full_name
        out.append(row)
    return out


@router.put("/overtime-profiles/{user_id}", response_model=OvertimeProfileOut)
async def upsert_overtime_profile(
    user_id: int, payload: OvertimeProfileIn, actor: User = Depends(_require_manage), db: AsyncSession = Depends(get_db)
) -> OvertimeProfileOut:
    target = await db.get(User, user_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Xodim topilmadi")

    existing = await db.scalar(select(OvertimeProfile).where(OvertimeProfile.user_id == user_id))
    before = None
    if existing is not None:
        before = {c.name: getattr(existing, c.name) for c in OvertimeProfile.__table__.columns if c.name != "id"}
        for field, value in payload.model_dump().items():
            setattr(existing, field, value)
        profile = existing
    else:
        profile = OvertimeProfile(user_id=user_id, **payload.model_dump())
        db.add(profile)
    profile.updated_by = actor.id

    db.add(
        AuditLog(
            actor_id=actor.id,
            action="overtime_profile_upserted",
            target_user_id=user_id,
            before=before,
            after=payload.model_dump(),
        )
    )
    await db.commit()
    await db.refresh(profile)
    row = OvertimeProfileOut.model_validate(profile, from_attributes=True)
    row.user_full_name = target.full_name
    return row


# ─────────────────────────────────────────────
# Qo'shimcha ish — kiritish/tasdiqlash
# ─────────────────────────────────────────────


@router.get("/overtime", response_model=list[OvertimeEntryOut])
async def list_overtime(
    period: str | None = None,
    status_filter: str | None = None,
    actor: User = Depends(_require_view),
    db: AsyncSession = Depends(get_db),
) -> list[OvertimeEntryOut]:
    q = select(OvertimeEntry, User.full_name).join(User, OvertimeEntry.user_id == User.id)
    if period:
        start, end = _period_bounds(period)
        q = q.where(OvertimeEntry.date >= start, OvertimeEntry.date < end)
    if status_filter:
        q = q.where(OvertimeEntry.status == status_filter)
    if actor.role == Role.rop.value:
        visible_ids = {u.id for u in await _visible_users(db, actor)}
        if not visible_ids:
            return []
        q = q.where(OvertimeEntry.user_id.in_(visible_ids))
    q = q.order_by(OvertimeEntry.date.desc())

    rows = []
    for entry, full_name in (await db.execute(q)).all():
        row = OvertimeEntryOut.model_validate(entry, from_attributes=True)
        row.user_full_name = full_name
        rows.append(row)
    return rows


@router.post("/overtime", response_model=OvertimeEntryOut)
async def create_overtime(
    payload: OvertimeEntryIn, actor: User = Depends(_require_manage), db: AsyncSession = Depends(get_db)
) -> OvertimeEntryOut:
    target = await db.get(User, payload.user_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Xodim topilmadi")
    existing = await db.scalar(
        select(OvertimeEntry).where(OvertimeEntry.user_id == payload.user_id, OvertimeEntry.date == payload.date)
    )
    if existing is not None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Bu kunga allaqachon qo'shimcha ish yozuvi bor")

    entry = OvertimeEntry(
        user_id=payload.user_id,
        date=payload.date,
        minutes=payload.minutes,
        source="manual",
        status=OvertimeEntryStatus.pending.value,
        note=payload.note,
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    row = OvertimeEntryOut.model_validate(entry, from_attributes=True)
    row.user_full_name = target.full_name
    return row


@router.post("/overtime/{entry_id}/decide", response_model=OvertimeEntryOut)
async def decide_overtime(
    entry_id: int,
    payload: OvertimeEntryDecide,
    actor: User = Depends(_require_manage),
    db: AsyncSession = Depends(get_db),
) -> OvertimeEntryOut:
    entry = await db.get(OvertimeEntry, entry_id)
    if entry is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Yozuv topilmadi")
    if entry.status != OvertimeEntryStatus.pending.value:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Bu yozuv allaqachon hal qilingan")

    entry.status = payload.status
    entry.decided_by = actor.id
    entry.decided_at = datetime.utcnow()

    db.add(
        AuditLog(
            actor_id=actor.id,
            action="overtime_entry_decided",
            target_user_id=entry.user_id,
            before={"status": "pending"},
            after={"status": payload.status, "minutes": entry.minutes, "date": entry.date.isoformat()},
        )
    )
    await db.commit()
    await db.refresh(entry)
    target = await db.get(User, entry.user_id)
    row = OvertimeEntryOut.model_validate(entry, from_attributes=True)
    row.user_full_name = target.full_name if target else None
    return row


# ─────────────────────────────────────────────
# Qo'lda qo'shimcha/ushlanma (avans va h.k.)
# ─────────────────────────────────────────────


@router.post("/adjustments", response_model=PayrollAdjustmentOut)
async def create_adjustment(
    payload: PayrollAdjustmentIn, actor: User = Depends(_require_manage), db: AsyncSession = Depends(get_db)
) -> PayrollAdjustment:
    target = await db.get(User, payload.user_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Xodim topilmadi")
    adj = PayrollAdjustment(
        user_id=payload.user_id,
        period=payload.period,
        kind=payload.kind,
        amount=payload.amount,
        reason=payload.reason,
        created_by=actor.id,
    )
    db.add(adj)
    db.add(
        AuditLog(
            actor_id=actor.id,
            action="payroll_adjustment_created",
            target_user_id=payload.user_id,
            before=None,
            after={"period": payload.period, "kind": payload.kind, "amount": payload.amount, "reason": payload.reason},
        )
    )
    await db.commit()
    await db.refresh(adj)
    return adj


@router.delete("/adjustments/{adjustment_id}")
async def delete_adjustment(
    adjustment_id: int, actor: User = Depends(_require_manage), db: AsyncSession = Depends(get_db)
) -> dict:
    adj = await db.get(PayrollAdjustment, adjustment_id)
    if adj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Yozuv topilmadi")
    db.add(
        AuditLog(
            actor_id=actor.id,
            action="payroll_adjustment_deleted",
            target_user_id=adj.user_id,
            before={"period": adj.period, "kind": adj.kind, "amount": float(adj.amount), "reason": adj.reason},
            after=None,
        )
    )
    await db.delete(adj)
    await db.commit()
    return {"deleted": True}


# ─────────────────────────────────────────────
# Hisob-kitob
# ─────────────────────────────────────────────


@router.get("/periods", response_model=list[PayrollPeriodOut])
async def list_periods(
    actor: User = Depends(_require_view), db: AsyncSession = Depends(get_db)
) -> list[PayrollPeriodOut]:
    """Hisoblangan barcha davrlar — sahifa davr tanlagichini to'ldirish uchun.
    E'TIBOR: literal "/periods" — bu route "/{period}" catch-all'idan OLDIN
    ro'yxatdan o'tishi SHART, aks holda FastAPI "periods" so'zini davr nomi
    deb talqin qilib qolardi."""
    periods = list(await db.scalars(select(PayrollPeriod).order_by(PayrollPeriod.period.desc())))
    out = []
    for pr in periods:
        rows = list(await db.scalars(select(Payslip).where(Payslip.period == pr.period)))
        if actor.role == Role.rop.value:
            visible_ids = {u.id for u in await _visible_users(db, actor)}
            rows = [r for r in rows if r.user_id in visible_ids]
        out.append(
            PayrollPeriodOut(
                period=pr.period,
                status=pr.status,
                locked=pr.locked,
                calculated_at=pr.calculated_at,
                approved_at=pr.approved_at,
                employee_count=len(rows),
                total_net=sum(float(r.net) for r in rows),
            )
        )
    return out


@router.get("/{period}/preflight", response_model=PayrollPreflightOut)
async def preflight(
    period: str, _actor: User = Depends(_require_manage), db: AsyncSession = Depends(get_db)
) -> PayrollPreflightOut:
    """Oylik hisobdan OLDINGI tekshiruv — 6-bo'lim. Attendance tayyorligi
    (Bosqich 0) + payrollga xos: stavkasiz xodim, hal qilinmagan qo'shimcha
    ish so'rovi. GET (o'qish-only) — plan qoralamasida POST deb yozilgan edi,
    lekin bu amal ma'lumot o'zgartirmagani uchun GET to'g'riroq (attendance
    `/readiness` bilan bir xil qoida)."""
    start, end = _period_bounds(period)
    last_day = date.fromordinal(end.toordinal() - 1)
    attendance_readiness = await collect_readiness(db, start, last_day)

    users = list(
        await db.scalars(select(User).where(User.role.in_(PAYROLL_TRACKED_ROLES), User.is_active.is_(True)))
    )
    names = {u.id: u.full_name for u in users}

    with_rate = set(
        await db.scalars(
            select(SalaryRate.user_id).where(SalaryRate.effective_from < end).distinct()
        )
    )
    no_salary_rate = [
        ReadinessIssue(user_id=u.id, full_name=u.full_name, detail="Oylik stavka kiritilmagan")
        for u in users
        if u.id not in with_rate
    ]

    pending_rows = list(
        await db.scalars(
            select(OvertimeEntry).where(
                OvertimeEntry.date >= start,
                OvertimeEntry.date < end,
                OvertimeEntry.status == OvertimeEntryStatus.pending.value,
            )
        )
    )
    pending_overtime = [
        ReadinessIssue(
            user_id=e.user_id, full_name=names.get(e.user_id, f"#{e.user_id}"), date=e.date,
            detail=f"{e.minutes} daqiqa — hali tasdiqlanmagan",
        )
        for e in pending_rows
    ]

    ok = attendance_readiness["ok"] and not no_salary_rate and not pending_overtime
    return PayrollPreflightOut(
        period=period,
        ok=ok,
        attendance=attendance_readiness,
        no_salary_rate=no_salary_rate,
        pending_overtime=pending_overtime,
    )


@router.post("/{period}/calculate")
async def calculate(
    period: str,
    payload: PayrollCalculateRequest,
    actor: User = Depends(_require_manage),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        result = await run_payroll(db, period, user_ids=payload.user_ids)
    except PayrollLocked as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))

    # HR/Boshliqqa "tayyor, tasdiqlaysizmi" xabari — GURUHGA EMAS, shaxsiy DM
    # (faqat rahbarlarga, individual xodim summasi ko'rsatilmaydi — jami
    # jamg'arma OK, chunki bu tashkilot darajasidagi raqam).
    rows = list(await db.scalars(select(Payslip).where(Payslip.period == period)))
    total = sum(float(p.net) for p in rows)
    managers = list(
        await db.scalars(
            select(User).where(User.role.in_((Role.hr.value, Role.boss.value)), User.telegram_id.isnot(None))
        )
    )
    for m in managers:
        await send_message(
            m.telegram_id,
            f"💰 Payroll tayyor ({period}): {result['calculated']} xodim, jami ~{total:,.0f} so'm. "
            f"Tasdiqlash uchun saytga kiring.".replace(",", " "),
        )
    # 8-bo'lim (Bosqich 7): barcha pul o'zgarishlari audit qilinadi — hisoblash
    # o'zi pul figurasini o'zgartiradi (garchi qulflamasa ham).
    db.add(
        AuditLog(
            actor_id=actor.id,
            action="payroll_calculated",
            target_user_id=None,
            before=None,
            after={"period": period, "calculated": result["calculated"], "total_net": total},
        )
    )
    await db.commit()
    return result


@router.get("/{period}", response_model=list[PayslipRow])
async def list_payslips(
    period: str, actor: User = Depends(_require_view), db: AsyncSession = Depends(get_db)
) -> list[PayslipRow]:
    rows = list(
        await db.scalars(select(Payslip).where(Payslip.period == period))
    )
    if actor.role == Role.rop.value:
        visible_ids = {u.id for u in await _visible_users(db, actor)}
        rows = [r for r in rows if r.user_id in visible_ids]

    names = {}
    if rows:
        result = await db.execute(select(User.id, User.full_name).where(User.id.in_([r.user_id for r in rows])))
        names = dict(result.all())

    return [
        PayslipRow(
            user_id=r.user_id,
            full_name=names.get(r.user_id, f"#{r.user_id}"),
            status=r.status,
            base_amount=float(r.base_amount),
            late_days=r.late_days,
            fined_late_days=r.fined_late_days,
            fine_amount=float(r.fine_amount),
            absent_days=r.absent_days,
            absent_deduction=float(r.absent_deduction),
            overtime_minutes=r.overtime_minutes,
            overtime_amount=float(r.overtime_amount),
            bonus_amount=float(r.bonus_amount),
            gross=float(r.gross),
            net=float(r.net),
        )
        for r in sorted(rows, key=lambda r: names.get(r.user_id, ""))
    ]


@router.get("/{period}/export")
async def export_payroll(
    period: str, actor: User = Depends(_require_view), db: AsyncSession = Depends(get_db)
) -> StreamingResponse:
    """Excel ish haqi varag'i — Bosqich 7. ROP faqat o'z jamoasini eksport
    qiladi (`list_payslips` bilan bir xil qamrov naqshi)."""
    user_ids = None
    if actor.role == Role.rop.value:
        user_ids = [u.id for u in await _visible_users(db, actor)]
    buffer = await build_payroll_xlsx(db, period, user_ids=user_ids)
    filename = f"oylik_{period}.xlsx"
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{period}/user/{user_id}", response_model=PayslipDetailOut)
async def payslip_detail(
    period: str, user_id: int, actor: User = Depends(_require_view), db: AsyncSession = Depends(get_db)
) -> PayslipDetailOut:
    target = await db.get(User, user_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Xodim topilmadi")
    if not can_view_payroll(actor, target):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Bu xodimning payroll ma'lumotini ko'rish huquqingiz yo'q")

    payslip = await db.scalar(select(Payslip).where(Payslip.user_id == user_id, Payslip.period == period))
    if payslip is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bu davr uchun hali hisoblanmagan")
    items = list(
        await db.scalars(
            select(PayslipItem).where(PayslipItem.payslip_id == payslip.id).order_by(PayslipItem.sort_order)
        )
    )
    return PayslipDetailOut(
        id=payslip.id,
        user_id=payslip.user_id,
        full_name=target.full_name,
        period=payslip.period,
        status=payslip.status,
        base_amount=float(payslip.base_amount),
        pay_basis=payslip.pay_basis,
        rate_snapshot=float(payslip.rate_snapshot) if payslip.rate_snapshot is not None else None,
        scheduled_days=payslip.scheduled_days,
        worked_days=payslip.worked_days,
        absent_days=payslip.absent_days,
        excused_days=payslip.excused_days,
        scheduled_minutes=payslip.scheduled_minutes,
        worked_minutes=payslip.worked_minutes,
        late_days=payslip.late_days,
        late_minutes=payslip.late_minutes,
        fined_late_days=payslip.fined_late_days,
        fined_late_minutes=payslip.fined_late_minutes,
        fine_amount=float(payslip.fine_amount),
        absent_deduction=float(payslip.absent_deduction),
        overtime_minutes=payslip.overtime_minutes,
        overtime_amount=float(payslip.overtime_amount),
        overtime_rate_snapshot=(
            float(payslip.overtime_rate_snapshot) if payslip.overtime_rate_snapshot is not None else None
        ),
        bonus_amount=float(payslip.bonus_amount),
        adjustments_plus=float(payslip.adjustments_plus),
        adjustments_minus=float(payslip.adjustments_minus),
        gross=float(payslip.gross),
        net=float(payslip.net),
        currency=payslip.currency,
        calculated_at=payslip.calculated_at,
        approved_at=payslip.approved_at,
        items=[PayslipItemOut.model_validate(i, from_attributes=True) for i in items],
        breakdown=payslip.breakdown,
    )


@router.post("/{period}/approve")
async def approve_period(
    period: str, actor: User = Depends(_require_manage), db: AsyncSession = Depends(get_db)
) -> dict:
    """Davrni tasdiqlaydi va QULFLAYDI (`locked=True`) — shu nuqtadan keyin
    `calculate` 409 qaytaradi (avval Dasturchi `reopen` qilishi kerak,
    Bosqich 3.5). Har bir xodimga shaxsiy DM boradi (guruhga EMAS —
    maxfiylik, 8.6-band)."""
    period_row = await db.scalar(select(PayrollPeriod).where(PayrollPeriod.period == period))
    if period_row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bu davr uchun hali hisoblanmagan")
    if period_row.locked:
        raise HTTPException(status.HTTP_409_CONFLICT, "Bu davr allaqachon tasdiqlangan")

    payslips = list(await db.scalars(select(Payslip).where(Payslip.period == period)))
    if not payslips:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Bu davr uchun payslip yo'q — avval hisoblang")

    now = datetime.utcnow()
    for p in payslips:
        p.status = "approved"
        p.approved_by = actor.id
        p.approved_at = now

    period_row.status = "approved"
    period_row.locked = True
    period_row.approved_by = actor.id
    period_row.approved_at = now

    db.add(
        AuditLog(
            actor_id=actor.id,
            action="payroll_period_approved",
            target_user_id=None,
            before=None,
            after={"period": period, "payslip_count": len(payslips)},
        )
    )
    await db.commit()

    user_ids = [p.user_id for p in payslips]
    result = await db.execute(select(User.id, User.telegram_id).where(User.id.in_(user_ids)))
    telegram_by_user = dict(result.all())
    for p in payslips:
        tg_id = telegram_by_user.get(p.user_id)
        if not tg_id:
            continue
        await send_message(
            tg_id,
            f"💵 {period} oyi uchun oyligingiz tasdiqlandi. Tafsilot uchun botdagi «Mening oyligim» "
            f"bo'limiga qarang.",
        )

    return {"period": period, "approved": len(payslips)}


# ─────────────────────────────────────────────
# Bot (X-Bot-Secret)
# ─────────────────────────────────────────────


@router.post("/{period}/calculate-cron", dependencies=[Depends(verify_bot_secret)])
async def calculate_cron(period: str, db: AsyncSession = Depends(get_db)) -> dict:
    """Scheduler chaqiruvi — Bosqich 6 (keyingi oyning 1-kuni ertalab, QAROR
    9-bo'lim savol 10). Muvaffaqiyatsiz bo'lsa xodimlarga payroll umuman
    hisoblanmaydi — natija har doim ochiq (Bonus jobi bilan bir xil naqsh)."""
    try:
        result = await run_payroll(db, period)
    except PayrollLocked as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    db.add(
        AuditLog(
            actor_id=None,  # scheduler/tizim tomonidan avtomatik hisoblanadi
            action="payroll_calculated",
            target_user_id=None,
            before=None,
            after={"period": period, "calculated": result["calculated"]},
        )
    )
    await db.commit()
    return result


class PayrollCalculateMonthlyRequest(BaseModel):
    period: str | None = None  # "YYYY-MM"; berilmasa avtomatik o'tgan oy (`bonuses.py` bilan bir xil naqsh)


@router.post("/calculate-monthly", dependencies=[Depends(verify_bot_secret)])
async def calculate_monthly_cron(
    payload: PayrollCalculateMonthlyRequest, db: AsyncSession = Depends(get_db)
) -> dict:
    """Scheduler — keyingi oyning 1-kuni ertalab (9-bo'lim, savol 10, QAROR).
    Davr `payload.period` berilmasa avtomatik "o'tgan oy" (`previous_period`) —
    chunki job ishga tushganda `today_local()` allaqachon YANGI oyga o'tgan
    bo'ladi. Muvaffaqiyatli hisoblansa `calculate` (qo'lda) bilan BIR XIL
    "Payroll tayyor" DM'ini HR/Boshliqqa yuboradi — avtomatik hisoblash ham,
    qo'lda ham HR uchun bir xil "tasdiqlash kerak" signalini beradi."""
    period = payload.period or previous_period(today_local())
    try:
        result = await run_payroll(db, period)
    except PayrollLocked as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))

    rows = list(await db.scalars(select(Payslip).where(Payslip.period == period)))
    total = sum(float(p.net) for p in rows)
    managers = list(
        await db.scalars(
            select(User).where(User.role.in_((Role.hr.value, Role.boss.value)), User.telegram_id.isnot(None))
        )
    )
    for m in managers:
        await send_message(
            m.telegram_id,
            f"💰 Payroll avtomatik hisoblandi ({period}): {result['calculated']} xodim, jami ~{total:,.0f} so'm. "
            f"Tasdiqlash uchun saytga kiring.".replace(",", " "),
        )
    db.add(
        AuditLog(
            actor_id=None,  # scheduler/tizim tomonidan avtomatik hisoblanadi
            action="payroll_calculated",
            target_user_id=None,
            before=None,
            after={"period": period, "calculated": result["calculated"], "total_net": total},
        )
    )
    await db.commit()
    return result


class PayrollDateTickRequest(BaseModel):
    # E'TIBOR: maydon nomi ataylab `target_date` (`date` EMAS) — pydantic
    # forward-ref baholashda maydon nomi o'z turi bilan bir xil bo'lsa
    # (`date: date | None`), sinf nazomasida `date` maydon qiymati bilan
    # SOYALANIB, tur eval'i "NoneType | NoneType" xatosini beradi.
    target_date: date | None = None  # berilmasa "kecha" (scheduler kunlik ishlatadi)


@router.post("/late-warnings-tick", dependencies=[Depends(verify_bot_secret)])
async def late_warnings_tick(
    payload: PayrollDateTickRequest, db: AsyncSession = Depends(get_db)
) -> dict:
    """Scheduler — kunlik (1.5-band, "Shaffoflik"). `payload.target_date`
    (odatda "kecha") shu oyda kimningdir bepul kechikish limitini birinchi
    marta OSHIRGAN yoki unga YAQINLASHTIRGAN bo'lsa — botga darhol shaxsiy
    xabar. Alohida "allaqachon yuborilganmi" jadval YO'Q — `late_limit_event_for`
    faqat ANIQ shu kunga tegishli voqeani tekshiradi, shuning uchun kuniga
    bir marta ishlatilsa tabiiy ravishda ikki marta yubormaydi."""
    target_date = payload.target_date or date.fromordinal(today_local().toordinal() - 1)
    users = list(
        await db.scalars(
            select(User).where(
                User.role.in_(PAYROLL_TRACKED_ROLES), User.is_active.is_(True), User.telegram_id.isnot(None)
            )
        )
    )
    warned = 0
    limit_reached = 0
    for user in users:
        event = await late_limit_event_for(db, user, target_date)
        if event is None:
            continue
        if event["kind"] == "limit_reached":
            fine = float(event["fine_per_day"]) if event["fine_per_day"] is not None else 0
            text = (
                "⚠️ Diqqat: bu oy bepul kechikish limitingiz tugadi. Bugundan boshlab har kechikkan "
                f"kunga {fine:,.0f} so'm jarima yoziladi.".replace(",", " ")
            )
            limit_reached += 1
        else:
            text = (
                f"🕐 Ogohlantirish: bepul kechikish limitingizdan atigi {event['remaining_minutes']} daqiqa "
                "qoldi. Keyingi kechikish jarima boshlanishiga olib kelishi mumkin."
            )
        await send_message(user.telegram_id, text)
        warned += 1
    return {"date": target_date.isoformat(), "checked": len(users), "warned": warned, "limit_reached": limit_reached}


@router.post("/overtime/auto-detect", dependencies=[Depends(verify_bot_secret)])
async def overtime_auto_detect(
    payload: PayrollDateTickRequest, db: AsyncSession = Depends(get_db)
) -> dict:
    """Scheduler — kunlik (1.3-band). `payload.target_date` (odatda "kecha")
    uchun check-out rejadagi tugash vaqtidan keyin bo'lgan, overtime-yoqilgan
    xodimlarga NOMZOD (`pending`) yaratadi — HR/rahbar tasdiqlamaguncha
    payslip hisobiga kirmaydi."""
    target_date = payload.target_date or date.fromordinal(today_local().toordinal() - 1)
    created = await detect_overtime_candidates(db, target_date)
    await db.commit()
    return {"date": target_date.isoformat(), "created": len(created)}


@router.get("/my/{telegram_id}", response_model=BotPayslipOut, dependencies=[Depends(verify_bot_secret)])
async def my_payslip(telegram_id: int, db: AsyncSession = Depends(get_db)) -> BotPayslipOut:
    """Xodimning oxirgi TASDIQLANGAN varaqasi — `draft`/`calculated` (hali
    tasdiqlanmagan, o'zgarishi mumkin) xodimga ko'rsatilmaydi."""
    user = await db.scalar(select(User).where(User.telegram_id == telegram_id))
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Foydalanuvchi topilmadi")
    payslip = await db.scalar(
        select(Payslip)
        .where(Payslip.user_id == user.id, Payslip.status == "approved")
        .order_by(Payslip.period.desc())
        .limit(1)
    )
    if payslip is None:
        return BotPayslipOut(calculated=False)
    return BotPayslipOut(
        calculated=True,
        period=payslip.period,
        base_amount=float(payslip.base_amount),
        fine_amount=float(payslip.fine_amount),
        absent_deduction=float(payslip.absent_deduction),
        overtime_amount=float(payslip.overtime_amount),
        bonus_amount=float(payslip.bonus_amount),
        net=float(payslip.net),
        currency=payslip.currency,
        approved_at=payslip.approved_at,
    )


async def _late_status_for_user(db: AsyncSession, user: User) -> BotLateStatusOut:
    """Joriy oyda kechikish holati — HALI hisoblanmagan (davom etayotgan) oy
    uchun JONLI hisoblanadi (Payslip'dan emas, chunki oy hali yakunlanmagan).
    1.5-band: xodimga oldindan ogohlantirish (bot va web CheckIn'da bir xil)."""
    period = today_local().strftime("%Y-%m")
    policy = await resolve_policy(db, user)
    days = await collect_attendance(db, user, period)
    late = compute_late_fine(days, policy)

    free_limit = policy.free_late_minutes_per_month if policy else None
    used = late["late_minutes"]
    remaining = max(0, free_limit - used) if free_limit is not None else None

    return BotLateStatusOut(
        period=period,
        free_limit_minutes=free_limit,
        used_minutes=used,
        remaining_minutes=remaining,
        fined_days_so_far=late["fined_days"],
        fine_per_day=float(policy.fine_per_day) if policy and policy.fine_per_day is not None else None,
    )


@router.get(
    "/my/{telegram_id}/late-status", response_model=BotLateStatusOut, dependencies=[Depends(verify_bot_secret)]
)
async def my_late_status(telegram_id: int, db: AsyncSession = Depends(get_db)) -> BotLateStatusOut:
    user = await db.scalar(select(User).where(User.telegram_id == telegram_id))
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Foydalanuvchi topilmadi")
    return await _late_status_for_user(db, user)


@router.get("/me/late-status", response_model=BotLateStatusOut)
async def my_late_status_web(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> BotLateStatusOut:
    """Web (JWT) versiyasi — CheckIn.tsx uchun. Xodim faqat O'ZINING holatini
    ko'radi (path'da user_id yo'q, tokendan olinadi)."""
    return await _late_status_for_user(db, user)
