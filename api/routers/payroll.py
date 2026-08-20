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
import datetime as dt
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Path, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.audit_json import row_to_dict
from api.deps import (
    assert_can_view,
    get_current_user,
    get_db,
    require_roles,
    scoped_user_ids,
    verify_bot_secret,
)
from api.schemas import (
    AdvanceIssueIn,
    MyAdvanceRow,
    MyAdvancesOut,
    AdvanceLimitOut,
    BotLateStatusOut,
    BotPayslipOut,
    FinePolicyIn,
    FinePolicyOut,
    KpiRateIn,
    KpiRateOut,
    OvertimeEntryDecide,
    OvertimeEntryIn,
    OvertimeEntryOut,
    OvertimeProfileIn,
    OvertimeProfileOut,
    AdvanceDecision,
    AdvanceIn,
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
    SalaryRateUpdate,
)
from api.services.advance import AdvanceLimit, limit_for as advance_limit_for
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
from api.notify import notify_user
from api.services.push import Category
from api.telegram_notify import inline_keyboard
from api.timeutil import today_local
from db.models import (
    PAYROLL_COUNTED_STATUSES,
    AuditLog,
    FinePolicy,
    KpiRate,
    OvertimeEntry,
    OvertimeEntryStatus,
    OvertimeProfile,
    PayrollAdjustment,
    PayrollAdjustmentCategory,
    PayrollAdjustmentKind,
    PayrollAdjustmentSource,
    PayrollAdjustmentStatus,
    PayrollPeriod,
    PayrollPeriodStatus,
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
# YAKUNIY tasdiq (davrni qulflash) va AVANSNI tasdiqlash — HR emas.
# Vazifalar ajratimi: pulni HR kiritadi, Boshliq tasdiqlaydi.
PAYROLL_FINAL_APPROVE_ROLES = (Role.boss.value, Role.dasturchi.value)


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


def _require_fine_policy_manage(actor: User = Depends(get_current_user)) -> User:
    """Kechikish/jarima QOIDASI uchun alohida darvoza: roli bo'yicha
    (hr/boss/dasturchi) YOKI shaxsan berilgan `can_edit_fine_policy`.

    NEGA `_require_manage` kengaytirilmadi: u stavka, qo'shimcha ish, oylik
    hisoblash va TASDIQLASH kabi amallarni ham qo'riqlaydi. Bitta bayroq
    bilan ularning hammasini ochib yuborish — masalan ROP o'z oyligini o'zi
    tasdiqlay olishi — mutlaqo boshqa xavf edi. Shuning uchun bayroq FAQAT
    shu darvozani ochadi."""
    if actor.role in PAYROLL_MANAGE_ROLES or actor.can_edit_fine_policy:
        return actor
    raise HTTPException(status.HTTP_403_FORBIDDEN, "Bu amal uchun ruxsat yo'q")


# Kechikish normasi huquqini BERADIGANLAR — Dasturchi yoki Boshliq (egasining
# qarori: "balkim hr o'zgartira olar balkim rop, uni kimgadir biriktirish
# funksiyasini dasturchi yoki boss hal qiladi"). HR bu yerda YO'Q: u normani
# o'zgartira oladi, lekin BOSHQALARGA huquq tarqata olmaydi.
FINE_POLICY_GRANT_ROLES = (Role.boss.value, Role.dasturchi.value)


class FinePolicyEditorGrant(BaseModel):
    granted: bool
    reason: str = Field(min_length=5, max_length=500)


@router.get("/fine-policy-editors")
async def list_fine_policy_editors(
    _actor: User = Depends(require_roles(*FINE_POLICY_GRANT_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Kechikish normasini o'zgartirish huquqi SHAXSAN berilganlar. Roli
    bo'yicha huquqi borlar (hr/boss/dasturchi) bu ro'yxatga kirmaydi."""
    rows = list(
        await db.scalars(
            select(User).where(User.can_edit_fine_policy.is_(True)).order_by(User.full_name)
        )
    )
    return [{"id": u.id, "full_name": u.full_name, "role": u.role, "is_active": u.is_active} for u in rows]


@router.post("/fine-policy-editors/{user_id}")
async def set_fine_policy_editor(
    user_id: int,
    payload: FinePolicyEditorGrant,
    actor: User = Depends(require_roles(*FINE_POLICY_GRANT_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Kechikish/jarima qoidasini o'zgartirish huquqini beradi/oladi.

    Berish auditga yoziladi — jarima qoidasi bevosita xodim haqiga ta'sir
    qiladi, ya'ni "kim bu huquqni kimga bergan" savoli keyinchalik albatta
    chiqadi."""
    target = await db.get(User, user_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Foydalanuvchi topilmadi")

    before = bool(target.can_edit_fine_policy)
    target.can_edit_fine_policy = payload.granted
    db.add(
        AuditLog(
            actor_id=actor.id,
            action="fine_policy_editor_set",
            target_user_id=user_id,
            before={"can_edit_fine_policy": before},
            after={"can_edit_fine_policy": payload.granted, "reason": payload.reason},
        )
    )
    await db.commit()
    return {"user_id": user_id, "can_edit_fine_policy": payload.granted}


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
async def list_policies(_actor: User = Depends(_require_fine_policy_manage), db: AsyncSession = Depends(get_db)):
    policies = list(await db.scalars(select(FinePolicy).order_by(FinePolicy.scope, FinePolicy.scope_id)))
    out: list[FinePolicyOut] = []
    for p in policies:
        row = FinePolicyOut.model_validate(p)
        row.scope_label = await _policy_label(db, p)
        out.append(row)
    return out


@router.put("/policies", response_model=FinePolicyOut)
async def upsert_policy(
    payload: FinePolicyIn, actor: User = Depends(_require_fine_policy_manage), db: AsyncSession = Depends(get_db)
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
        # `row_to_dict` SHART: xom ORM qiymatlari ichida `Decimal` bo'ladi
        # (fine_per_day, absent_fine, cap...) va u JSON ustunga yozilmaydi —
        # audit commit paytida yiqilib, QOIDA O'ZGARISHI ham qaytarilardi.
        before = row_to_dict(existing, exclude=("id",))
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
    # S-02: ish haqidan ushlab qolish HUQUQIY jihatdan xavfli tanlov —
    # alohida, qidirsa darhol topiladigan audit yozuvi qoldiriladi.
    # (Umumiy `fine_policy_upserted` yozuvi ichida ko'milib ketmasin: bu
    # aynan tekshiruvda so'raladigan qaror.)
    if payload.fine_remainder_mode == "from_salary" and (
        before is None or before.get("fine_remainder_mode") != "from_salary"
    ):
        db.add(
            AuditLog(
                actor_id=actor.id,
                action="fine_remainder_from_salary_enabled",
                target_user_id=payload.scope_id if payload.scope == "user" else None,
                before={"fine_remainder_mode": before.get("fine_remainder_mode") if before else None},
                after={
                    "scope": payload.scope,
                    "scope_id": payload.scope_id,
                    "fine_remainder_mode": "from_salary",
                    "izoh": "Ushlanma qoldig'i ISH HAQIDAN ushlanadigan qilib qo'yildi",
                },
            )
        )
    await db.commit()
    await db.refresh(policy)
    row = FinePolicyOut.model_validate(policy)
    row.scope_label = await _policy_label(db, policy)
    return row


@router.delete("/policies/{policy_id}")
async def delete_policy(
    policy_id: int, actor: User = Depends(_require_fine_policy_manage), db: AsyncSession = Depends(get_db)
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


@router.patch("/rates/{rate_id}", response_model=SalaryRateOut)
async def update_rate(
    rate_id: int,
    payload: SalaryRateUpdate,
    actor: User = Depends(_require_manage),
    db: AsyncSession = Depends(get_db),
) -> SalaryRate:
    """Kiritilgan stavkani tahrirlash (2026-08-13, egasining talabi).

    NEGA KERAK: `POST /rates` bir sanaga ikkinchi stavkani rad etib
    «avval eskisini o'zgartiring» derdi, lekin HR uchun o'zgartiradigan
    yo'l umuman yo'q edi — faqat Dasturchining `/admin/records` sahifasida.
    Xato summa kiritilsa uni tuzatib bo'lmasdi.

    CHEKLOV ATAYLAB QO'YILMADI (egasining qarori: "HR har qanday stavkani
    tahrirlay olsin"). Muhimi: bu tahrir ALLAQACHON HISOBLANGAN payslip'larni
    O'ZGARTIRMAYDI — ular saqlangan summalar bilan turadi. Yangi summa faqat
    davr qayta hisoblanganda kuchga kiradi, qulflangan davrni esa qayta
    hisoblab bo'lmaydi. Ya'ni tasdiqlangan oylik o'z-o'zidan buzilmaydi.

    Butun o'zgarish auditga tushadi (`before`/`after`)."""
    rate = await db.get(SalaryRate, rate_id)
    if rate is None or rate.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Stavka topilmadi")

    fields = payload.model_fields_set
    before = row_to_dict(rate, exclude=("created_at",))

    if "effective_from" in fields and payload.effective_from != rate.effective_from:
        # UNIQUE(user_id, effective_from) yumshoq o'chirilganlarni ham qamraydi
        # — shuning uchun bu tekshiruv `deleted_at`ga QARAMAYDI, aks holda
        # baza darajasida IntegrityError bilan yiqilardi.
        clash = await db.scalar(
            select(SalaryRate).where(
                SalaryRate.user_id == rate.user_id,
                SalaryRate.effective_from == payload.effective_from,
                SalaryRate.id != rate.id,
            )
        )
        if clash is not None:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Bu sanada shu xodimning boshqa stavkasi bor — avval o'shani o'zgartiring",
            )
        rate.effective_from = payload.effective_from

    if "amount" in fields and payload.amount is not None:
        rate.amount = payload.amount
    if "pay_basis" in fields and payload.pay_basis is not None:
        rate.pay_basis = payload.pay_basis
    if "note" in fields:
        rate.note = payload.note  # None yuborilsa — izoh tozalanadi
    rate.changed_by = actor.id

    db.add(
        AuditLog(
            actor_id=actor.id,
            action="salary_rate_updated",
            target_user_id=rate.user_id,
            before=before,
            after=row_to_dict(rate, exclude=("created_at",)),
        )
    )
    await db.commit()
    await db.refresh(rate)
    return rate


# ─────────────────────────────────────────────
# KPI stavkalari (bonus) — 2026-08-08
# ─────────────────────────────────────────────


async def _scope_label(db: AsyncSession, scope: str, scope_id: int | None) -> str | None:
    """`_policy_label` bilan bir xil mantiq, lekin har qanday qamrov uchun."""
    if scope == "user" and scope_id:
        u = await db.get(User, scope_id)
        return u.full_name if u else f"#{scope_id}"
    if scope == "position" and scope_id:
        pos = await db.get(Position, scope_id)
        return pos.name if pos else f"#{scope_id}"
    return None


@router.get("/kpi-rates", response_model=list[KpiRateOut])
async def list_kpi_rates(
    _actor: User = Depends(_require_manage), db: AsyncSession = Depends(get_db)
) -> list[KpiRateOut]:
    """Barcha KPI stavkalari — TARIX bilan (har o'zgarish alohida qator).

    Yumshoq o'chirilganlar ko'rinmaydi (`SalaryRate` bilan bir xil qoida) —
    ularni Dasturchi rejimi orqali ko'rish/tiklash mumkin."""
    rows = list(
        await db.scalars(
            select(KpiRate)
            .where(KpiRate.deleted_at.is_(None))
            .order_by(KpiRate.metric, KpiRate.scope, KpiRate.effective_from.desc())
        )
    )
    out: list[KpiRateOut] = []
    for r in rows:
        item = KpiRateOut.model_validate(r)
        item.scope_label = await _scope_label(db, r.scope, r.scope_id)
        out.append(item)
    return out


@router.post("/kpi-rates", response_model=KpiRateOut)
async def create_kpi_rate(
    payload: KpiRateIn, actor: User = Depends(_require_manage), db: AsyncSession = Depends(get_db)
) -> KpiRateOut:
    """Yangi KPI stavkasi. `SalaryRate` bilan BIR XIL naqsh: mavjud qator
    HECH QACHON o'zgartirilmaydi, faqat yangi `effective_from` bilan qator
    qo'shiladi — o'tgan oy bonusi buzilmaydi.

    Nishon mavjudligi tekshiriladi: lavozim/xodim o'chirilgan bo'lsa stavka
    hech qachon qo'llanmasdi va bu jimgina sezilmay qolardi."""
    if payload.scope == "user":
        if await db.get(User, payload.scope_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Xodim topilmadi")
    elif payload.scope == "position":
        if await db.get(Position, payload.scope_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Lavozim topilmadi")

    existing = await db.scalar(
        select(KpiRate).where(
            KpiRate.scope == payload.scope,
            KpiRate.scope_id.is_(None) if payload.scope_id is None else KpiRate.scope_id == payload.scope_id,
            KpiRate.metric == payload.metric,
            KpiRate.effective_from == payload.effective_from,
        )
    )
    if existing is not None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Bu sanaga shu ko'rsatkich uchun stavka allaqachon kiritilgan",
        )

    rate = KpiRate(
        scope=payload.scope,
        scope_id=payload.scope_id,
        metric=payload.metric,
        amount=payload.amount,
        effective_from=payload.effective_from,
        note=payload.note,
        changed_by=actor.id,
    )
    db.add(rate)
    db.add(
        AuditLog(
            actor_id=actor.id,
            action="kpi_rate_created",
            target_user_id=payload.scope_id if payload.scope == "user" else None,
            before=None,
            # `payload` maydonlari allaqachon oddiy turlar (float/str/date),
            # lekin `date` JSON'ga aylanmaydi — shuning uchun ISO satr.
            after={
                "scope": payload.scope,
                "scope_id": payload.scope_id,
                "metric": payload.metric,
                "amount": payload.amount,
                "effective_from": payload.effective_from.isoformat(),
            },
        )
    )
    await db.commit()
    await db.refresh(rate)
    out = KpiRateOut.model_validate(rate)
    out.scope_label = await _scope_label(db, rate.scope, rate.scope_id)
    return out


@router.get("/overtime-profiles", response_model=list[OvertimeProfileOut])
async def list_overtime_profiles(
    _actor: User = Depends(_require_manage), db: AsyncSession = Depends(get_db)
) -> list[OvertimeProfileOut]:
    # `outerjoin` — global qatorda `user_id` NULL, `join` uni tashlab
    # yuborardi va sozlamalar sahifasi «global profil yo'q» deb ko'rsatardi.
    result = await db.execute(
        select(OvertimeProfile, User.full_name).outerjoin(User, OvertimeProfile.user_id == User.id)
    )
    out = []
    for profile, full_name in result.all():
        row = OvertimeProfileOut.model_validate(profile, from_attributes=True)
        row.user_full_name = full_name
        out.append(row)
    return out


class OvertimeBulkApply(BaseModel):
    """Bir necha xodimga bir vaqtda profil qo'llash."""

    user_ids: list[int]
    profile: OvertimeProfileIn


@router.post("/overtime-profiles/bulk")
async def bulk_apply_overtime_profile(
    payload: OvertimeBulkApply, actor: User = Depends(_require_manage), db: AsyncSession = Depends(get_db)
) -> dict:
    """Tanlangan xodimlarga BIR VAQTDA profil yozadi (egasining talabi
    2026-08-18: «hammaga birdaniga yoki bir nechta xodimga yoki bitta
    xodimga yoqish»).

    Uchala holat ham shu bitta yo'l bilan qoplanadi:
      • bitta xodim   → `user_ids` da bitta id;
      • bir nechtasi  → ro'yxat;
      • HAMMASI       → `user_ids` bo'sh ro'yxat (barcha faol, davomat
        kuzatiladigan xodim olinadi).

    ⚠️ «Hammaga» uchun GLOBAL profil ham bor (`PUT .../global`) va odatda
    U AFZAL: yangi ishga kirgan xodim o'z-o'zidan qamrab olinadi. Bu
    endpoint esa har xodimga ALOHIDA qator yozadi — global qoidadan
    farq qiladigan guruh kerak bo'lganda ishlatiladi."""
    if payload.user_ids:
        users = list(await db.scalars(select(User).where(User.id.in_(payload.user_ids))))
        topilmadi = set(payload.user_ids) - {u.id for u in users}
        if topilmadi:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, f"Xodim topilmadi: {sorted(topilmadi)}"
            )
    else:
        users = list(
            await db.scalars(
                select(User).where(
                    User.role.in_(PAYROLL_TRACKED_ROLES), User.is_active.is_(True)
                )
            )
        )

    qiymatlar = payload.profile.model_dump()
    mavjud = {
        p.user_id: p
        for p in await db.scalars(
            select(OvertimeProfile).where(
                OvertimeProfile.scope == "user",
                OvertimeProfile.user_id.in_([u.id for u in users]),
            )
        )
    }

    yangilandi = yaratildi = 0
    for u in users:
        profile = mavjud.get(u.id)
        if profile is None:
            db.add(OvertimeProfile(user_id=u.id, scope="user", updated_by=actor.id, **qiymatlar))
            yaratildi += 1
        else:
            for field, value in qiymatlar.items():
                setattr(profile, field, value)
            profile.updated_by = actor.id
            yangilandi += 1

    # Audit BITTA yozuv — 20 ta alohida qator jurnalni ishlatib bo'lmas
    # holga keltirardi (ommaviy amalda naqsh `overtime_bulk_decided` bilan
    # bir xil).
    db.add(
        AuditLog(
            actor_id=actor.id,
            action="overtime_profile_bulk_applied",
            target_user_id=None,
            before=None,
            after={
                "xodimlar": [u.id for u in users],
                "soni": len(users),
                "yaratildi": yaratildi,
                "yangilandi": yangilandi,
                "hammaga": not payload.user_ids,
                **qiymatlar,
            },
        )
    )
    await db.commit()
    return {"applied": len(users), "created": yaratildi, "updated": yangilandi}


@router.put("/overtime-profiles/global", response_model=OvertimeProfileOut)
async def upsert_global_overtime_profile(
    payload: OvertimeProfileIn, actor: User = Depends(_require_manage), db: AsyncSession = Depends(get_db)
) -> OvertimeProfileOut:
    """BARCHA xodimga amal qiladigan default qo'shimcha ish profili (§3.2).

    NEGA KERAK: profil har bir xodim uchun alohida edi va `enabled` default
    `False` — ya'ni HR har kimga qo'lda profil ochmaguncha qo'shimcha ish
    UMUMAN hisoblanmasdi. Jonli bazada yoqilgan profil 0 ta edi, shu sababli
    «avtomat hisoblab bersin» talabi bajarilmayotgan edi.

    Bu route `/{user_id}` dan OLDIN e'lon qilinishi shart — aks holda
    FastAPI «global» so'zini `user_id` deb talqin qilib 422 qaytarardi."""
    existing = await db.scalar(select(OvertimeProfile).where(OvertimeProfile.scope == "global"))
    before = None
    if existing is not None:
        before = row_to_dict(existing, exclude=("id",))
        for field, value in payload.model_dump().items():
            setattr(existing, field, value)
        profile = existing
    else:
        profile = OvertimeProfile(user_id=None, scope="global", **payload.model_dump())
        db.add(profile)
    profile.updated_by = actor.id

    db.add(
        AuditLog(
            actor_id=actor.id,
            action="overtime_profile_global_upserted",
            target_user_id=None,
            before=before,
            after=payload.model_dump(),
        )
    )
    await db.commit()
    await db.refresh(profile)
    return OvertimeProfileOut.model_validate(profile, from_attributes=True)


@router.put("/overtime-profiles/{user_id}", response_model=OvertimeProfileOut)
async def upsert_overtime_profile(
    user_id: int, payload: OvertimeProfileIn, actor: User = Depends(_require_manage), db: AsyncSession = Depends(get_db)
) -> OvertimeProfileOut:
    target = await db.get(User, user_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Xodim topilmadi")

    existing = await db.scalar(
        select(OvertimeProfile).where(
            OvertimeProfile.user_id == user_id, OvertimeProfile.scope == "user"
        )
    )
    before = None
    if existing is not None:
        # Yuqoridagi bilan bir xil sabab: `multiplier`/`fixed_rate_per_hour`
        # — `Decimal`, `updated_at` — `datetime`.
        before = row_to_dict(existing, exclude=("id",))
        for field, value in payload.model_dump().items():
            setattr(existing, field, value)
        profile = existing
    else:
        profile = OvertimeProfile(user_id=user_id, scope="user", **payload.model_dump())
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


class PayrollDateTickRequest(BaseModel):
    # E'TIBOR: maydon nomi ataylab `target_date` (`date` EMAS) — pydantic
    # forward-ref baholashda maydon nomi o'z turi bilan bir xil bo'lsa
    # (`date: date | None`), sinf nazomasida `date` maydon qiymati bilan
    # SOYALANIB, tur eval'i "NoneType | NoneType" xatosini beradi.
    target_date: date | None = None  # berilmasa "kecha" (scheduler kunlik ishlatadi)


class OvertimeBulkDecide(BaseModel):
    period: str  # "YYYY-MM"
    status: str = OvertimeEntryStatus.approved.value


@router.post("/overtime/bulk-decide")
async def bulk_decide_overtime(
    payload: OvertimeBulkDecide, actor: User = Depends(_require_manage), db: AsyncSession = Depends(get_db)
) -> dict:
    """Bir oydagi BARCHA kutilayotgan qo'shimcha ish yozuvini bir bosishda
    hal qiladi (§3.2 to'siq C).

    NEGA: nomzodlar har kuni avtomatik yaratiladi va `pending` bo'lib
    tug'iladi. 20 xodim × 22 ish kuni = ~440 yozuv — HR ularni birma-bir
    bosolmaydi, natijada hech biri tasdiqlanmay qolib «qo'shimcha ish
    ishlamayapti» degan taassurot tug'ilardi.

    Tasdiq bosqichining O'ZI qoladi (pul xavfsizligi) — faqat mehnati
    kamayadi. Kim tasdiqlagani har bir yozuvda va auditda saqlanadi."""
    if payload.status not in (OvertimeEntryStatus.approved.value, OvertimeEntryStatus.rejected.value):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "status 'approved' yoki 'rejected' bo'lishi kerak")
    start, end = _period_bounds(payload.period)

    rows = list(
        await db.scalars(
            select(OvertimeEntry).where(
                OvertimeEntry.date >= start,
                OvertimeEntry.date < end,
                OvertimeEntry.status == OvertimeEntryStatus.pending.value,
            )
        )
    )
    now = datetime.utcnow()
    for entry in rows:
        entry.status = payload.status
        entry.decided_by = actor.id
        entry.decided_at = now

    if rows:
        # Audit BITTA yozuv — 440 ta alohida qator audit jurnalini
        # ishlatib bo'lmas holga keltirardi. Tafsilot uchun daqiqalar jami
        # va xodimlar soni saqlanadi.
        db.add(
            AuditLog(
                actor_id=actor.id,
                action="overtime_bulk_decided",
                target_user_id=None,
                before={"pending": len(rows)},
                after={
                    "period": payload.period,
                    "status": payload.status,
                    "count": len(rows),
                    "users": len({e.user_id for e in rows}),
                    "total_minutes": sum(e.minutes for e in rows),
                },
            )
        )
    await db.commit()
    return {"period": payload.period, "status": payload.status, "decided": len(rows)}


@router.post("/overtime/detect-now")
async def overtime_detect_now(
    payload: PayrollDateTickRequest, actor: User = Depends(_require_manage), db: AsyncSession = Depends(get_db)
) -> dict:
    """«Hozir hisoblab ber» — saytdan (JWT bilan) qo'shimcha ish nomzodlarini
    darhol yaratadi (§3.2 to'siq B).

    NEGA: avtomatik aniqlash cron orqali KECHASI 01:00 da ishlaydi, ya'ni
    bugungi farq ertaga ertalab paydo bo'ladi. Buni bilmagan HR «ishlamayapti»
    deb o'ylardi. Endi kutmasdan bosib ko'rish mumkin.

    Default sana — KECHA (cron bilan bir xil): bugungi kun hali tugamagan,
    xodim ishdan chiqmagan bo'lishi mumkin."""
    target_date = payload.target_date or date.fromordinal(today_local().toordinal() - 1)
    created = await detect_overtime_candidates(db, target_date)
    db.add(
        AuditLog(
            actor_id=actor.id,
            action="overtime_detect_now",
            target_user_id=None,
            before=None,
            after={"date": target_date.isoformat(), "created": len(created)},
        )
    )
    await db.commit()
    return {"date": target_date.isoformat(), "created": len(created)}


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


# ─────────────────────────────────────────────
# Avans (2026-08-13) — HR kiritadi, Boshliq tasdiqlaydi
# ─────────────────────────────────────────────


def _fmt_money(amount: float) -> str:
    """1200000.0 → '1 200 000 so'm' — bot/handlers/payroll.py dagi ko'rinish
    bilan bir xil (xodim ikki joyda bir xil summani boshqacha ko'rmasin)."""
    return f"{int(round(amount)):,}".replace(",", " ") + " so'm"


# Dublikat mezoni (Avans TZ A-01). Aniq tenglik yaramaydi: HR «2 000 000»
# o'rniga «2 000 500» yozishi yoki sanani bir kun surishi mumkin — bu baribir
# o'sha avans. Shu sababli oraliq bilan solishtiramiz.
_DUP_AMOUNT_RATIO = 0.10   # summa 10% ichida bo'lsa — «yaqin»
_DUP_DAYS = 7              # sana 7 kun ichida bo'lsa — «yaqin»


async def _find_duplicate_advance(
    db: AsyncSession,
    user_id: int,
    period: str,
    amount: float,
    issued_on: dt.date,
) -> PayrollAdjustment | None:
    """Shu xodimga shu davrda yaqin summa va yaqin sana bilan avans bormi?

    Rad etilganlar hisobga OLINMAYDI — ular oylikka kirmaydi, ya'ni takror
    kiritish xavfi yo'q (aksincha, rad etilgandan keyin qayta kiritish
    odatiy holat)."""
    rows = await db.scalars(
        select(PayrollAdjustment).where(
            PayrollAdjustment.user_id == user_id,
            PayrollAdjustment.period == period,
            PayrollAdjustment.category == PayrollAdjustmentCategory.advance.value,
            PayrollAdjustment.status != PayrollAdjustmentStatus.rejected.value,
            # O'chirilgan avans dublikat sifatida ogohlantirmasin (A-05).
            PayrollAdjustment.deleted_at.is_(None),
        )
    )
    tolerance = max(amount, 1.0) * _DUP_AMOUNT_RATIO
    for row in rows:
        if abs(float(row.amount) - amount) > tolerance:
            continue
        if abs((_advance_ref_date(row) - issued_on).days) > _DUP_DAYS:
            continue
        return row
    return None


def _advance_ref_date(adj: PayrollAdjustment) -> dt.date:
    """Avansning «qachonligi» — dublikat solishtiruvi uchun.

    A-04 dan keyin `issued_on` faqat TO'LANGANDA to'ladi, ya'ni yangi
    kiritilgan avansda u `NULL`. Bunday qatorni sanasiz deb tashlab
    yuborsak, dublikat qo'riqchisi eng ko'p kerak bo'lgan holatda —
    ketma-ket ikki marta kiritishda — jim qolardi. Shuning uchun
    zaxira sana: kiritilgan kun."""
    if adj.issued_on is not None:
        return adj.issued_on
    return adj.created_at.date() if adj.created_at else dt.date.min


def _duplicate_message(dup: PayrollAdjustment) -> str:
    """Ogohlantirish matni — HR qaror qabul qilishi uchun YETARLI ma'lumot
    bo'lsin: qachon, qancha, qaysi yo'ldan kelgan."""
    where = "xodim arizasi orqali" if dup.source == PayrollAdjustmentSource.request.value else "qo'lda"
    # A-04 dan keyin yangi avansda `issued_on` bo'sh bo'ladi (pul hali
    # berilmagan) — bunday holatda kiritilgan kun ko'rsatiladi, aks holda
    # ogohlantirish «sanasiz» bo'lib, HR uni tanib olmasdi.
    if dup.issued_on is not None:
        when = f"to'langan {dup.issued_on.strftime('%d.%m.%Y')}"
    else:
        when = f"kiritilgan {_advance_ref_date(dup).strftime('%d.%m.%Y')}"
    return (
        f"Bu xodimga shu davrda yaqin avans allaqachon bor: "
        f"{_fmt_money(float(dup.amount))}, {when} ({where}). "
        f"Ikki marta ayirilib ketmasin — takror kiritmoqchi bo'lsangiz tasdiqlang."
    )


# Sabab majburiy bo'lganda O'TMAYDIGAN matnlar (A-05 / TZ #8). Bo'sh
# maydonni majburiy qilishning ma'nosi yo'q, agar «avans» deb yozib
# o'tib ketish mumkin bo'lsa — qoida faqat bezak bo'lib qolardi.
_MEANINGLESS_REASONS = {"avans", "avans kerak", "kerak", "pul", "pul kerak", "-", "...", "sabab"}
_MIN_REASON_LEN = 5


async def _check_reason(db: AsyncSession, target: User, reason: str) -> None:
    """Sabab qoidasi HR panelidan yoqilgan bo'lsa tekshiradi.

    DEFAULT O'CHIQ: C blokdagi bot oqimida xodim tugma bosib avans
    so'raydi va matn yozmaydi — majburiy qilsak o'sha oqim buzilardi."""
    policy = await resolve_policy(db, target)
    if policy is None or not policy.advance_reason_required:
        return
    text = (reason or "").strip()
    if len(text) < _MIN_REASON_LEN or text.lower() in _MEANINGLESS_REASONS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Sabab kamida {_MIN_REASON_LEN} belgidan iborat va MA'NOLI bo'lishi kerak "
            "(«avans», «kerak» kabi matnlar qabul qilinmaydi). "
            "Qoidani HR «Ish haqi → Sozlamalar» dan o'zgartirishi mumkin.",
        )


async def _close_pending_advances(db: AsyncSession, period: str, actor: User) -> dict:
    """Davr qulflanganda hali `pending` bo'lgan avanslar bilan nima qilish
    (A-06 / Avans TZ #5).

    MUAMMO: ilgari qoida umuman yo'q edi va `pending` avans qulflangan
    davrda abadiy osilib qolardi — oylikka ham kirmasdi, rad ham
    etilmasdi, xodim esa javob kutib turardi.

    Har bir xodimning O'Z qoidasi o'qiladi (`resolve_policy`: xodim >
    lavozim > global), chunki lavozimga alohida siyosat qo'yish mumkin.

    `carry` (default) — avans KEYINGI davrga ko'chiriladi va tasdiq
    kutishda qoladi. `cancel` — rad etiladi va xodimga sabab bilan
    xabar boradi.

    ⚠️ Chaqiruvchi `commit` qilmaydi — bu funksiya `db.add`/maydon
    o'zgartirish bilan cheklanadi, davr qulfi bilan BITTA tranzaksiyada
    yakunlanadi (yarim ko'chirilgan holat bo'lmasin)."""
    rows = list(
        await db.scalars(
            select(PayrollAdjustment).where(
                PayrollAdjustment.period == period,
                PayrollAdjustment.category == PayrollAdjustmentCategory.advance.value,
                PayrollAdjustment.status == PayrollAdjustmentStatus.pending.value,
                PayrollAdjustment.deleted_at.is_(None),
            )
        )
    )
    if not rows:
        return {"carried": 0, "cancelled": 0}

    next_period = _next_period(period)
    carried = cancelled = 0
    notify: list = []
    for adj in rows:
        target = await db.get(User, adj.user_id)
        policy = await resolve_policy(db, target) if target is not None else None
        mode = policy.advance_pending_on_close if policy is not None else "carry"
        before = row_to_dict(adj, exclude=("created_at",))
        if mode == "cancel":
            adj.status = PayrollAdjustmentStatus.rejected.value
            adj.decided_by = actor.id
            adj.decided_at = datetime.utcnow()
            adj.decided_note = f"{period} davri yopildi — tasdiqlanmagan avans avtomatik bekor qilindi"
            cancelled += 1
            if target is not None:
                notify.append((target, adj, "cancel"))
        else:
            adj.period = next_period
            carried += 1
            if target is not None:
                notify.append((target, adj, "carry"))
        db.add(
            AuditLog(
                actor_id=actor.id,
                action="advance_period_closed",
                target_user_id=adj.user_id,
                before=before,
                after=row_to_dict(adj, exclude=("created_at",)),
            )
        )
    return {"carried": carried, "cancelled": cancelled, "notify": notify}


def _next_period(period: str) -> str:
    """'2026-08' -> '2026-09'."""
    y, m = (int(x) for x in period.split("-"))
    return f"{y + 1}-01" if m == 12 else f"{y}-{m + 1:02d}"


def _limit_message(info: AdvanceLimit, requested: float) -> str:
    """Rad javobi HR uchun QARORGA yetarli bo'lsin: qancha so'raldi, qancha
    mumkin va nega. «Chegaradan oshdi» degan quruq matn HR ni raqamni
    taxmin qilib qayta-qayta urinishga majbur qilardi."""
    if info.limit <= 0:
        sabab = info.reason or "chegara 0"
        return f"Bu xodimga hozir avans berib bo'lmaydi ({sabab})."
    return (
        f"So'ralgan summa chegaradan oshdi. Ruxsat etilgan: {_fmt_money(info.limit)} "
        f"(so'ralgan: {_fmt_money(requested)}). Hisob: sof oylik {_fmt_money(info.net_salary)}, "
        f"{info.worked_days}/{info.scheduled_days} kun ishlangan, "
        f"shu oyda olingan avans {_fmt_money(info.taken)}."
    )


async def _adjustment_out(db: AsyncSession, adj: PayrollAdjustment) -> PayrollAdjustmentOut:
    """Yozuvni ismlar bilan boyitadi — jadval har qator uchun alohida so'rov
    yubormasin (ro'yxat sahifasi aynan shu shaklda ko'rsatadi)."""
    out = PayrollAdjustmentOut.model_validate(adj, from_attributes=True)
    target = await db.get(User, adj.user_id)
    creator = await db.get(User, adj.created_by)
    out.full_name = target.full_name if target else None
    out.created_by_name = creator.full_name if creator else None
    if adj.decided_by:
        decider = await db.get(User, adj.decided_by)
        out.decided_by_name = decider.full_name if decider else None
    if adj.issued_by:
        issuer = await db.get(User, adj.issued_by)
        out.issued_by_name = issuer.full_name if issuer else None
    return out


@router.get("/adjustments", response_model=list[PayrollAdjustmentOut])
async def list_adjustments(
    period: str | None = None,
    user_id: int | None = None,
    category: str | None = None,
    _actor: User = Depends(_require_manage),
    db: AsyncSession = Depends(get_db),
) -> list[PayrollAdjustmentOut]:
    """Qo'lda qo'shimcha/ushlanma va avanslar ro'yxati.

    Ilgari bu endpoint umuman YO'Q edi — yozuvni yaratish va o'chirish
    mumkin bo'lgani holda, ro'yxatini ko'rish imkoni bo'lmagan (ya'ni web
    panelda avans oynasini qurib bo'lmasdi)."""
    # A-05: o'chirilganlar ro'yxatda ko'rinmaydi. Ular BAZADA qoladi
    # (audit va «qayerga ketdi?» savoli uchun), lekin kundalik ishda
    # ko'rinib turishi HR ni chalg'itardi.
    stmt = select(PayrollAdjustment).where(PayrollAdjustment.deleted_at.is_(None))
    if period:
        stmt = stmt.where(PayrollAdjustment.period == period)
    if user_id:
        stmt = stmt.where(PayrollAdjustment.user_id == user_id)
    if category:
        stmt = stmt.where(PayrollAdjustment.category == category)
    rows = list(await db.scalars(stmt.order_by(PayrollAdjustment.created_at.desc())))
    return [await _adjustment_out(db, a) for a in rows]


@router.get("/advances/limit", response_model=AdvanceLimitOut)
async def advance_limit(
    user_id: int,
    period: str | None = None,
    _actor: User = Depends(_require_manage),
    db: AsyncSession = Depends(get_db),
) -> AdvanceLimitOut:
    """Xodimga hozir eng ko'pi bilan qancha avans berish mumkin.

    Forma buni xodim tanlangan zahoti ko'rsatadi — HR kiritgandan KEYIN
    400 olib, raqamni taxmin qilib qayta urinmasin."""
    target = await db.get(User, user_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Xodim topilmadi")
    info = await advance_limit_for(db, target, period=period)
    return AdvanceLimitOut(**asdict(info))


@router.post("/advances", response_model=PayrollAdjustmentOut)
async def create_advance(
    payload: AdvanceIn, actor: User = Depends(_require_manage), db: AsyncSession = Depends(get_db)
) -> PayrollAdjustmentOut:
    """HR avans kiritadi — `pending` holatida, oylikka HALI KIRMAYDI.

    Yo'nalish (`minus`) serverda qat'iy: avans har doim ushlanma, mijoz uni
    tanlay olmaydi. Boshliqqa tasdiq so'rab xabar boradi."""
    target = await db.get(User, payload.user_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Xodim topilmadi")

    # Qulflangan davrga avans kiritish mantiqsiz — u baribir hisobga
    # kirmaydi (davr qayta hisoblanmaydi), lekin HR uni "kiritdim" deb
    # o'ylab qolardi.
    period_row = await db.scalar(select(PayrollPeriod).where(PayrollPeriod.period == payload.period))
    if period_row is not None and period_row.locked:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Bu davr qulflangan — avans hisobga kirmaydi. Avval Dasturchi davrni ochishi kerak.",
        )

    await _check_reason(db, target, payload.reason)

    # A-04: pul berilgan sana KIRITISHDA yozilmaydi. Dublikat qo'riqchisi
    # va chegara uchun mos yozuv sanasi — bugun.
    entry_date = today_local()

    # ── Dublikat qo'riqchisi (Avans TZ A-01) ──
    # Xodim ariza bergan avans ham, HR qo'lda kiritgani ham AYNAN shu
    # jadvalga tushadi. Manba ko'rinmagani uchun HR ariza orqali allaqachon
    # yozilgan avansni takror kiritishi mumkin edi — pul ikki marta
    # ayirilardi. Taqiq emas, ogohlantirish: bir oyda ikki marta avans
    # olish haqiqiy holat, shuning uchun HR `confirm_duplicate` bilan
    # bosib o'tadi.
    if not payload.confirm_duplicate:
        dup = await _find_duplicate_advance(
            db, payload.user_id, payload.period, payload.amount, entry_date
        )
        if dup is not None:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail={
                    "code": "advance_duplicate",
                    "message": _duplicate_message(dup),
                    "existing_id": dup.id,
                },
            )

    # ── Chegara tekshiruvi (Avans TZ A-03) ──
    # Chegarasiz avans oy oxirida payslipni MANFIY qilishi mumkin edi va
    # bunday xato qaytarib olinmaydi: pul allaqachon qo'lda.
    limit_info = await advance_limit_for(db, target, period=payload.period)
    over_limit = payload.amount > limit_info.limit
    if over_limit:
        if not payload.override_limit:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "advance_over_limit",
                    "message": _limit_message(limit_info, payload.amount),
                    "limit": limit_info.limit,
                    "reason": limit_info.reason,
                },
            )
        # Istisno — faqat Boshliq/Dasturchi va faqat sabab bilan.
        if actor.role not in PAYROLL_FINAL_APPROVE_ROLES:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "Chegaradan oshiq avansni faqat Boshliq yoki Dasturchi kirita oladi.",
            )
        if not (payload.override_reason or "").strip():
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Chegaradan oshiq kiritish sababini yozing — u auditga tushadi.",
            )

    adj = PayrollAdjustment(
        user_id=payload.user_id,
        period=payload.period,
        kind=PayrollAdjustmentKind.minus.value,
        amount=payload.amount,
        reason=payload.reason,
        created_by=actor.id,
        category=PayrollAdjustmentCategory.advance.value,
        status=PayrollAdjustmentStatus.pending.value,
        # `issued_on` ATAYLAB bo'sh — uni faqat «To'lab berildi» yozadi.
        source=PayrollAdjustmentSource.hr_manual.value,
    )
    db.add(adj)
    db.add(
        AuditLog(
            actor_id=actor.id,
            # Istisno alohida amal nomi bilan yoziladi — auditda uni
            # oddiy kiritishdan ajratib qidirish mumkin bo'lsin.
            action="advance_over_limit" if over_limit else "advance_created",
            target_user_id=payload.user_id,
            before=None,
            after={
                "period": payload.period,
                "amount": payload.amount,
                "entry_date": entry_date.isoformat(),
                "reason": payload.reason,
                **(
                    {
                        "limit": limit_info.limit,
                        "limit_reason": limit_info.reason,
                        "override_reason": (payload.override_reason or "").strip(),
                    }
                    if over_limit
                    else {}
                ),
            },
        )
    )
    await db.commit()
    await db.refresh(adj)

    bosses = list(
        await db.scalars(
            select(User).where(
                User.role.in_(PAYROLL_FINAL_APPROVE_ROLES), User.telegram_id.isnot(None)
            )
        )
    )
    for b in bosses:
        await notify_user(
            db,
            b,
            Category.APPROVALS,
            f"💵 <b>Avans tasdig'i kutilmoqda</b>\n\n"
            f"Xodim: {target.full_name}\n"
            f"Summa: {_fmt_money(payload.amount)}\n"
            f"Davr: {payload.period}\n"
            f"Sabab: {payload.reason}\n\n"
            f"Kiritdi: {actor.full_name}\n"
            # A-04: pul HALI berilmagan — Boshliq buni bilib qaror qilsin.
            f"<i>Pul hali berilmagan — siz tasdiqlagach kassa to'laydi.</i>",
            data={"path": "/payroll"},
        )
    return await _adjustment_out(db, adj)


@router.post("/advances/{adjustment_id}/decide", response_model=PayrollAdjustmentOut)
async def decide_advance(
    adjustment_id: int,
    payload: AdvanceDecision,
    actor: User = Depends(require_roles(*PAYROLL_FINAL_APPROVE_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> PayrollAdjustmentOut:
    """Boshliq qarori. Tasdiqlangach avans oylikdan ayiriladi va XODIMGA
    xabar boradi (egasining qarori: xodim ko'rsin — oy oxirida "nega kam?"
    degan savol chiqmasin)."""
    adj = await db.get(PayrollAdjustment, adjustment_id)
    if adj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Yozuv topilmadi")
    if adj.category != PayrollAdjustmentCategory.advance.value:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Bu yozuv avans emas")
    if adj.status != PayrollAdjustmentStatus.pending.value:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Bu avans bo'yicha qaror allaqachon qabul qilingan")

    before = row_to_dict(adj, exclude=("created_at",))
    adj.status = (
        PayrollAdjustmentStatus.approved.value if payload.approve else PayrollAdjustmentStatus.rejected.value
    )
    adj.decided_by = actor.id
    adj.decided_at = datetime.utcnow()
    adj.decided_note = payload.note
    db.add(
        AuditLog(
            actor_id=actor.id,
            action="advance_approved" if payload.approve else "advance_rejected",
            target_user_id=adj.user_id,
            before=before,
            after=row_to_dict(adj, exclude=("created_at",)),
        )
    )
    await db.commit()
    await db.refresh(adj)

    target = await db.get(User, adj.user_id)
    if payload.approve and target is not None:
        await notify_user(
            db,
            target,
            Category.DECISIONS,
            f"💵 <b>Avans tasdiqlandi</b>\n\n"
            f"Summa: {_fmt_money(float(adj.amount))}\n\n"
            f"Bu summa <b>{adj.period}</b> oyligingizdan ayiriladi.\n"
            # A-04: tasdiq — RUXSAT, pul emas. Xodim «tasdiqlandi» xabarini
            # ko'rib pulni allaqachon berilgan deb o'ylab qolmasin.
            f"<i>Pulni kassadan olganingizda tizimda belgilanadi.</i>",
            data={"path": "/me/payroll"},
        )
    return await _adjustment_out(db, adj)


@router.post("/advances/{adjustment_id}/issue", response_model=PayrollAdjustmentOut)
async def issue_advance(
    adjustment_id: int,
    payload: AdvanceIssueIn,
    actor: User = Depends(_require_manage),
    db: AsyncSession = Depends(get_db),
) -> PayrollAdjustmentOut:
    """«To'lab berildi» — kassa pulni QO'LGA berganini belgilaydi (A-04).

    Faqat `approved` dan `issued` ga o'tish mumkin. `pending` dan to'g'ridan
    to'g'ri o'tib bo'lmaydi — bu ajratimning butun ma'nosi: pul Boshliq
    ruxsatidan KEYIN beriladi, aks holda rad javobi kelganda pul qaytmaydi.

    ⚠️ PUL O'ZGARMAYDI: `issued` ham `approved` kabi oylikka kiradi
    (`PAYROLL_COUNTED_STATUSES`)."""
    adj = await db.get(PayrollAdjustment, adjustment_id)
    if adj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Yozuv topilmadi")
    if adj.category != PayrollAdjustmentCategory.advance.value:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Bu yozuv avans emas")
    if adj.status == PayrollAdjustmentStatus.issued.value:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Bu avans allaqachon to'langan deb belgilangan"
        )
    if adj.status != PayrollAdjustmentStatus.approved.value:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Avval Boshliq tasdiqlashi kerak — tasdiqlanmagan avansni "
            "to'langan deb belgilab bo'lmaydi.",
        )

    issued_on = payload.issued_on or today_local()
    if issued_on > today_local():
        # Kelajakdagi sana — pul hali berilmagan, ya'ni belgilash erta.
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Berilgan sana kelajakda bo'lishi mumkin emas"
        )

    before = row_to_dict(adj, exclude=("created_at",))
    adj.status = PayrollAdjustmentStatus.issued.value
    adj.issued_on = issued_on
    adj.issued_by = actor.id
    adj.issued_at = datetime.utcnow()
    if payload.note:
        adj.decided_note = payload.note
    db.add(
        AuditLog(
            actor_id=actor.id,
            action="advance_issued",
            target_user_id=adj.user_id,
            before=before,
            after=row_to_dict(adj, exclude=("created_at",)),
        )
    )
    await db.commit()
    await db.refresh(adj)

    target = await db.get(User, adj.user_id)
    if target is not None:
        await notify_user(
            db,
            target,
            Category.DECISIONS,
            f"💵 <b>Avans to'lab berildi</b>\n\n"
            f"Summa: {_fmt_money(float(adj.amount))}\n"
            f"Berilgan sana: {issued_on.strftime('%d.%m.%Y')}\n\n"
            f"Bu summa <b>{adj.period}</b> oyligingizdan ayiriladi.",
            data={"path": "/me/payroll"},
        )
    return await _adjustment_out(db, adj)


@router.delete("/adjustments/{adjustment_id}")
async def delete_adjustment(
    adjustment_id: int,
    reason: str | None = None,
    actor: User = Depends(_require_manage),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """YUMSHOQ o'chirish (A-05) — qator bazada qoladi, `deleted_at` qo'yiladi.

    NEGA butunlay o'chirilmaydi: pul yozuvini yo'qotish «bu avans qayerga
    ketdi?» degan savolga javobsiz qoldiradi. Qator qolsa, audit va
    tekshiruv har doim mumkin; barcha o'qish `deleted_at IS NULL` bilan
    filtrlanadi, ya'ni oylikka ham, ro'yxatga ham kirmaydi.

    HUQUQ: HR faqat HALI QAROR QILINMAGAN (`pending`) avansni o'chira
    oladi. Tasdiqlangan yoki to'langan pulni bekor qilish — Boshliq/
    Dasturchi ishi: u yerda pul allaqachon harakatlangan bo'lishi mumkin."""
    adj = await db.get(PayrollAdjustment, adjustment_id)
    if adj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Yozuv topilmadi")
    if adj.deleted_at is not None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Bu yozuv allaqachon o'chirilgan")

    is_final = adj.status in PAYROLL_COUNTED_STATUSES
    if is_final and actor.role not in PAYROLL_FINAL_APPROVE_ROLES:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Tasdiqlangan yoki to'langan yozuvni faqat Boshliq/Dasturchi o'chira oladi.",
        )

    before = row_to_dict(adj, exclude=("created_at",))
    adj.deleted_at = datetime.utcnow()
    adj.deleted_by = actor.id
    adj.deleted_reason = (reason or "").strip() or None
    db.add(
        AuditLog(
            actor_id=actor.id,
            action="payroll_adjustment_deleted",
            target_user_id=adj.user_id,
            before=before,
            after=row_to_dict(adj, exclude=("created_at",)),
        )
    )
    await db.commit()
    return {"deleted": True, "soft": True}


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
    # HR tasdiqlaganlarning ismini BITTA so'rovda olamiz (davr soniga
    # ko'paytirilgan N+1 bo'lmasin).
    hr_ids = {pr.hr_approved_by for pr in periods if pr.hr_approved_by}
    hr_names = {
        u.id: u.full_name
        for u in (await db.scalars(select(User).where(User.id.in_(hr_ids))) if hr_ids else [])
    }
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
                hr_approved_at=pr.hr_approved_at,
                hr_approved_name=hr_names.get(pr.hr_approved_by),
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

    # ── §5.3: davomat yozuvi UMUMAN yo'q kunlar ──
    # NEGA MUHIM: `collect_attendance` yozuvi yo'q ish kunini «kelmagan» deb
    # sanaydi va oylikdan kunlik ulushni ayiradi. Yozuv esa ikki sababdan
    # yo'q bo'lishi mumkin: (a) xodim rostdan kelmagan — ayirma o'rinli;
    # (b) kechqurungi `write_absent_records` o'sha kuni ishlamagan (cron
    # o'chgan, tizim yangi ko'tarilgan) — bu holda xodim BEGUNOH jazolanadi.
    # Tizim ikkalasini farqlay olmaydi, shuning uchun HR ga KO'RSATAMIZ.
    #
    # `collect_attendance` xodim boshiga ~2 so'rov qiladi. Bu preflight
    # allaqachon og'ir (`collect_readiness`) va §4.2 dan keyin sahifada
    # BIR MARTA so'raladi — qo'shimcha yuk maqbul.
    # Ro'yxat chegaralangan: juda eski davr so'ralsa (hech kimda yozuv yo'q)
    # 15 xodim × 26 kun = 390 element bo'lib javob shishib ketardi.
    MISSING_LIMIT = 200
    missing_attendance: list[ReadinessIssue] = []
    for u in users:
        if len(missing_attendance) >= MISSING_LIMIT:
            break
        for d in await collect_attendance(db, u, period):
            if d["is_working"] and d["status"] == "absent" and d["attendance"] is None:
                missing_attendance.append(
                    ReadinessIssue(
                        user_id=u.id,
                        full_name=u.full_name,
                        date=d["date"],
                        detail="Davomat yozuvi umuman yo'q — «kelmagan» deb sanaladi",
                    )
                )

    # ── A-06: hali tasdiqlanmagan avanslar ──
    # Davr yopilgach ular sozlamaga ko'ra ko'chadi yoki bekor bo'ladi —
    # ikkalasi ham HR bilmagan holda sodir bo'lmasin.
    pending_adv_rows = list(
        await db.scalars(
            select(PayrollAdjustment).where(
                PayrollAdjustment.period == period,
                PayrollAdjustment.category == PayrollAdjustmentCategory.advance.value,
                PayrollAdjustment.status == PayrollAdjustmentStatus.pending.value,
                PayrollAdjustment.deleted_at.is_(None),
            )
        )
    )
    pending_advances = [
        ReadinessIssue(
            user_id=a.user_id,
            full_name=names.get(a.user_id, f"#{a.user_id}"),
            date=a.issued_on,
            detail=f"{_fmt_money(float(a.amount))} — hali tasdiqlanmagan",
        )
        for a in pending_adv_rows
    ]

    ok = (
        attendance_readiness["ok"]
        and not no_salary_rate
        and not pending_overtime
        and not missing_attendance
        # Tasdiqlanmagan avans hisobni BUZMAYDI (u oylikka kirmaydi), lekin
        # davr yopilishi uning taqdirini hal qiladi — HR ko'rmay o'tmasin.
        and not pending_advances
    )
    return PayrollPreflightOut(
        period=period,
        ok=ok,
        attendance=attendance_readiness,
        no_salary_rate=no_salary_rate,
        pending_overtime=pending_overtime,
        missing_attendance=missing_attendance,
        pending_advances=pending_advances,
    )


class PayrollCalcStatusOut(BaseModel):
    """Fon rejimidagi hisoblash holati — sayt shu endpointni 3 soniyada bir
    so'rab «12/20 xodim» progressini ko'rsatadi."""

    period: str
    state: str  # idle | queued | running | done | error
    progress: int
    total: int
    error: str | None = None
    started_at: datetime | None = None
    calculated_at: datetime | None = None


@router.post("/{period}/calculate", status_code=status.HTTP_202_ACCEPTED)
async def calculate(
    period: str,
    payload: PayrollCalculateRequest,
    actor: User = Depends(_require_manage),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Hisoblashni NAVBATGA qo'yadi va DARHOL qaytadi (§4.3).

    Ilgari bu endpoint ishning o'zini bajarardi — 20 xodim × ~12 SQL, keyin
    har rahbarga Telegram/FCM. cPanel'da Passenger konkurentligi = 1, ya'ni
    tugma bosilgan zahoti BUTUN sayt 10-40 soniyaga navbatga tushardi.

    Endi bu yerda faqat yengil UPDATE bor; og'ir ishni alohida cron JARAYONI
    (`api/services/payroll_jobs.py::payroll_tick`) bajaradi. Sayt esa
    `GET /payroll/{period}/status` orqali progressni kuzatadi."""
    # Qulf tekshiruvi ATAYLAB shu yerda: HR «qulflangan» xabarini navbatni
    # kutmasdan, darhol ko'rishi kerak.
    period_row = await db.scalar(select(PayrollPeriod).where(PayrollPeriod.period == period))
    if period_row is not None and period_row.locked:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"«{period}» davri qulflangan — avval qulfni ochish kerak"
        )
    if period_row is not None and period_row.calc_state in ("queued", "running"):
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"«{period}» allaqachon hisoblanmoqda — tugashini kuting"
        )

    if period_row is None:
        period_row = PayrollPeriod(period=period, status=PayrollPeriodStatus.draft.value)
        db.add(period_row)
        await db.flush()

    # Jami xodim sonini OLDINDAN bilib qo'yamiz — sahifa «0/15» ni darhol
    # ko'rsatsin, birinchi xodim hisoblanguncha «0/0» turmasin.
    count_query = select(func.count(User.id)).where(
        User.role.in_(PAYROLL_TRACKED_ROLES), User.is_active.is_(True)
    )
    if payload.user_ids is not None:
        count_query = count_query.where(User.id.in_(payload.user_ids))
    total = int(await db.scalar(count_query) or 0)

    period_row.calc_state = "queued"
    period_row.calc_requested_by = actor.id
    period_row.calc_requested_at = datetime.utcnow()
    period_row.calc_started_at = None
    period_row.calc_progress = 0
    period_row.calc_total = total
    period_row.calc_error = None
    period_row.calc_user_ids = list(payload.user_ids) if payload.user_ids is not None else None
    await db.commit()
    return {"period": period, "queued": True, "total": total}


@router.get("/{period}/status", response_model=PayrollCalcStatusOut)
async def calc_status(
    period: str, _actor: User = Depends(_require_manage), db: AsyncSession = Depends(get_db)
) -> PayrollCalcStatusOut:
    row = await db.scalar(select(PayrollPeriod).where(PayrollPeriod.period == period))
    if row is None:
        return PayrollCalcStatusOut(period=period, state="idle", progress=0, total=0)
    return PayrollCalcStatusOut(
        period=period,
        state=row.calc_state or "idle",
        progress=row.calc_progress or 0,
        total=row.calc_total or 0,
        error=row.calc_error,
        started_at=row.calc_started_at,
        calculated_at=row.calculated_at,
    )


@router.post("/tick", dependencies=[Depends(verify_bot_secret)])
async def payroll_queue_tick(db: AsyncSession = Depends(get_db)) -> dict:
    """Navbatdagi davrni hisoblaydi — Docker/scheduler rejimi va testlar uchun.

    cPanel'da bu HTTP yo'l ISHLATILMAYDI: `scripts/cron_tick.py` xuddi shu
    servisni o'z jarayonida chaqiradi, shunda og'irlik Passenger'ga
    umuman tegmaydi."""
    from api.services.payroll_jobs import payroll_tick

    return await payroll_tick(db)


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
    period: str = Path(pattern=r"^\d{4}-\d{2}$"),
    actor: User = Depends(_require_view),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Excel ish haqi varag'i — Bosqich 7. ROP faqat o'z jamoasini eksport
    qiladi (`list_payslips` bilan bir xil qamrov naqshi).

    `period` naqsh bilan cheklangan (`api/schemas.py` dagi bilan bir xil):
    u pastda `Content-Disposition` SARLAVHASIGA to'g'ridan-to'g'ri
    qo'yiladi, ya'ni tekshirilmasa qo'shtirnoqni yopib, sarlavhaga begona
    parametr qo'shish mumkin edi."""
    # S-06 «Tuzoq»: EKSPORT ham markazlashgan qamrovdan o'tadi. TZ buni
    # alohida aytgan — eksport odatda unutiladi va butun jadval Excel'ga
    # tushib ketadi.
    allowed = await scoped_user_ids(actor, db)
    user_ids = None if allowed is None else sorted(allowed)
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
    # S-06: qamrov MARKAZLASHGAN qatlamdan. Begona xodim so'ralsa 404 —
    # 403 «bunday xodim bor» degan ma'lumotni bergan bo'lardi.
    await assert_can_view(actor, user_id, db)
    target = await db.get(User, user_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Xodim topilmadi")

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


# `PAYROLL_FINAL_APPROVE_ROLES` fayl boshida (94-qator) — avans tasdig'i ham
# xuddi shu darvozadan o'tadi, u esa bu yerdan OLDIN e'lon qilingan.
# Yakuniy tasdiq — FAQAT Boshliq/Dasturchi. HR bu yerda ATAYLAB yo'q:
# vazifalarni ajratishning butun mohiyati shu (2026-08-08, egasining talabi
# "hr uni belgilaydi, boss boshliq uni tasdiqlaydi").


@router.post("/{period}/hr-approve")
async def hr_approve_period(
    period: str, actor: User = Depends(_require_manage), db: AsyncSession = Depends(get_db)
) -> dict:
    """HR bosqichi: «tekshirdim, tayyor». QULFLAMAYDI va pulni o'zgartirmaydi.

    NEGA ALOHIDA BOSQICH: ilgari HR o'zi hisoblab, o'zi tasdiqlab, davrni
    qulflab qo'yardi — bitta odam butun pul jarayonini yakunlardi. Endi HR
    faqat "tayyor" deb belgilaydi, Boshliqqa xabar ketadi, yakuniy qulf esa
    Boshliqda.

    Bu bosqichdan keyin ham qayta hisoblash MUMKIN (qulf yo'q) — HR xato
    topsa tuzatib, qaytadan "tayyor" deyishi kerak emas, holat saqlanadi.
    """
    period_row = await db.scalar(select(PayrollPeriod).where(PayrollPeriod.period == period))
    if period_row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bu davr uchun hali hisoblanmagan")
    if period_row.locked:
        raise HTTPException(status.HTTP_409_CONFLICT, "Bu davr allaqachon tasdiqlangan")

    payslips_count = len(list(await db.scalars(select(Payslip).where(Payslip.period == period))))
    if payslips_count == 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Bu davr uchun payslip yo'q — avval hisoblang")

    period_row.status = PayrollPeriodStatus.hr_approved.value
    period_row.hr_approved_by = actor.id
    period_row.hr_approved_at = datetime.utcnow()
    db.add(
        AuditLog(
            actor_id=actor.id,
            action="payroll_period_hr_approved",
            target_user_id=None,
            before=None,
            after={"period": period, "payslip_count": payslips_count},
        )
    )
    await db.commit()

    # Boshliqqa xabar — busiz HR "tayyor" deb qo'yadi-yu, hech kim bilmaydi.
    bosses = list(
        await db.scalars(
            select(User).where(
                User.role.in_(PAYROLL_FINAL_APPROVE_ROLES), User.telegram_id.isnot(None)
            )
        )
    )
    for b in bosses:
        await notify_user(
            db,
            b,
            Category.APPROVALS,
            f"✅ {actor.full_name} oylikni tekshirdi ({period}, {payslips_count} xodim). "
            f"Yakuniy tasdiq sizda.",
            data={"path": "/payroll"},
        )
    return {"period": period, "status": period_row.status, "payslip_count": payslips_count}


@router.post("/{period}/approve")
async def approve_period(
    period: str,
    actor: User = Depends(require_roles(*PAYROLL_FINAL_APPROVE_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """YAKUNIY tasdiq — davrni QULFLAYDI (`locked=True`). Faqat Boshliq/
    Dasturchi. Shu nuqtadan keyin `calculate` 409 qaytaradi (avval Dasturchi
    `reopen` qilishi kerak, Bosqich 3.5). Har bir xodimga shaxsiy DM boradi
    (guruhga EMAS — maxfiylik, 8.6-band).

    AVVAL HR BOSQICHI O'TISHI SHART: aks holda ajratishning ma'nosi
    qolmasdi — Boshliq HR tekshirmagan raqamni qulflab qo'yardi."""
    period_row = await db.scalar(select(PayrollPeriod).where(PayrollPeriod.period == period))
    if period_row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bu davr uchun hali hisoblanmagan")
    if period_row.locked:
        raise HTTPException(status.HTTP_409_CONFLICT, "Bu davr allaqachon tasdiqlangan")
    if period_row.status != PayrollPeriodStatus.hr_approved.value:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Avval HR tekshirib «tayyor» deb belgilashi kerak",
        )

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

    # A-06: hali tasdiqlanmagan avanslar sozlamaga muvofiq ishlanadi —
    # davr qulfi bilan BITTA tranzaksiyada (yarim ko'chirilgan holat
    # bo'lmasin).
    advance_result = await _close_pending_advances(db, period, actor)

    db.add(
        AuditLog(
            actor_id=actor.id,
            action="payroll_period_approved",
            target_user_id=None,
            before=None,
            after={
                "period": period,
                "payslip_count": len(payslips),
                "advances_carried": advance_result.get("carried", 0),
                "advances_cancelled": advance_result.get("cancelled", 0),
            },
        )
    )
    await db.commit()

    # Ilgari faqat `telegram_id` olinardi; push uchun `User` obyekti kerak
    # (toifa sozlamasi va qurilma ro'yxati foydalanuvchiga bog'langan).
    user_ids = [p.user_id for p in payslips]
    users_by_id = {
        u.id: u for u in await db.scalars(select(User).where(User.id.in_(user_ids)))
    }
    for p in payslips:
        emp = users_by_id.get(p.user_id)
        if emp is None:
            continue
        await notify_user(
            db,
            emp,
            Category.DECISIONS,
            f"💵 {period} oyi uchun oyligingiz tasdiqlandi. Tafsilot uchun botdagi «Mening oyligim» "
            f"bo'limiga qarang.",
            # 1.5-band (shaffoflik): hisobga rozi bo'lmasa — bir bosishda
            # e'tiroz, davr oldindan to'ldirilgan holda. `force_telegram`
            # SHART: tugma faqat botda ishlaydi (api/notify.py:66-72).
            reply_markup=inline_keyboard([[("⚖️ E'tiroz bildirish", f"appeal_payslip:{period}")]]),
            force_telegram=True,
            data={"path": "/me/payroll"},
        )

    # A-06: avansi ko'chirilgan/bekor qilingan xodimga ALOHIDA xabar.
    # «Oyligingiz tasdiqlandi» xabarining ichiga qo'shib yuborilmaydi —
    # bu boshqa voqea va u yo'qolib ketmasligi kerak.
    for emp, adj, mode in advance_result.get("notify", []):
        if mode == "carry":
            text = (
                f"💵 <b>Avans so'rovingiz keyingi oyga ko'chdi</b>\n\n"
                f"Summa: {_fmt_money(float(adj.amount))}\n"
                f"{period} davri yopildi, so'rov hali tasdiqlanmagan edi — u "
                f"<b>{adj.period}</b> davrida tasdiq kutishda qoladi."
            )
        else:
            text = (
                f"💵 <b>Avans so'rovingiz bekor qilindi</b>\n\n"
                f"Summa: {_fmt_money(float(adj.amount))}\n"
                f"{period} davri yopildi, so'rov esa tasdiqlanmagan edi. "
                f"Kerak bo'lsa yangi so'rov yuboring."
            )
        await notify_user(db, emp, Category.DECISIONS, text, data={"path": "/me/payroll"})

    return {
        "period": period,
        "approved": len(payslips),
        "advances_carried": advance_result.get("carried", 0),
        "advances_cancelled": advance_result.get("cancelled", 0),
    }


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
        await notify_user(
            db,
            m,
            Category.APPROVALS,
            f"💰 Payroll avtomatik hisoblandi ({period}): {result['calculated']} xodim, jami ~{total:,.0f} so'm. "
            f"Tasdiqlash uchun saytga kiring.".replace(",", " "),
            data={"path": "/payroll"},
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
                f"kunga {fine:,.0f} so'm ushlanma yoziladi.".replace(",", " ")
            )
            limit_reached += 1
        else:
            text = (
                f"🕐 Ogohlantirish: bepul kechikish limitingizdan atigi {event['remaining_minutes']} daqiqa "
                "qoldi. Keyingi kechikish ushlanma boshlanishiga olib kelishi mumkin."
            )
        await notify_user(db, user, Category.LATE_WARNING, text, data={"path": "/check-in"})
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


async def _latest_payslip_for_user(db: AsyncSession, user: User) -> BotPayslipOut:
    """Xodimning oxirgi TASDIQLANGAN varaqasi — `draft`/`calculated` (hali
    tasdiqlanmagan, o'zgarishi mumkin) xodimga ko'rsatilmaydi.

    Bot ham, web ham shu yordamchini chaqiradi (`_late_status_for_user` bilan
    bir xil naqsh) — mantiq ikki joyda takrorlanmasligi uchun."""
    payslip = await db.scalar(
        select(Payslip)
        .where(Payslip.user_id == user.id, Payslip.status == "approved")
        .order_by(Payslip.period.desc())
        .limit(1)
    )
    if payslip is None:
        return BotPayslipOut(calculated=False)

    # Avansni qolgan ushlanmalardan AJRATAMIZ: xodim uchun «Avans» — o'zi
    # olgan pul (tushunarli), «Ushlanma» esa boshqa narsa. Bittasiga
    # qo'shib yuborilsa xodim summani taniy olmasdi.
    advance_total = await db.scalar(
        select(func.coalesce(func.sum(PayrollAdjustment.amount), 0)).where(
            PayrollAdjustment.user_id == user.id,
            PayrollAdjustment.period == payslip.period,
            PayrollAdjustment.category == PayrollAdjustmentCategory.advance.value,
            # `issued` ham kiradi (A-04): payslip uni ayirgan, shuning uchun
            # bu yerda ham sanalishi SHART — aks holda quyidagi
            # «adjustments_minus - advance» ayirmasi ishlamay, xodim bitta
            # summani ikki marta ko'rardi.
            PayrollAdjustment.status.in_(PAYROLL_COUNTED_STATUSES),
            PayrollAdjustment.deleted_at.is_(None),
        )
    )
    advance = float(advance_total or 0)
    return BotPayslipOut(
        calculated=True,
        period=payslip.period,
        base_amount=float(payslip.base_amount),
        fine_amount=float(payslip.fine_amount),
        absent_deduction=float(payslip.absent_deduction),
        overtime_amount=float(payslip.overtime_amount),
        bonus_amount=float(payslip.bonus_amount),
        advance_amount=advance,
        adjustments_plus=float(payslip.adjustments_plus),
        # Avans allaqachon alohida ko'rsatilgani uchun uni bu yerdan
        # chiqaramiz — aks holda xodim bitta summani IKKI marta ko'rardi.
        adjustments_minus=max(float(payslip.adjustments_minus) - advance, 0.0),
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


async def _my_advances(db: AsyncSession, user: User) -> MyAdvancesOut:
    """Xodimning JORIY oydagi avanslari va qolgan chegarasi (A-06 / TZ #6).

    Bot va kabinet AYNAN shu funksiyani chaqiradi — ikki joyda ikki xil
    raqam chiqmasin."""
    period = today_local().strftime("%Y-%m")
    rows = list(
        await db.scalars(
            select(PayrollAdjustment)
            .where(
                PayrollAdjustment.user_id == user.id,
                PayrollAdjustment.period == period,
                PayrollAdjustment.category == PayrollAdjustmentCategory.advance.value,
                PayrollAdjustment.deleted_at.is_(None),
            )
            .order_by(PayrollAdjustment.created_at.desc())
        )
    )
    info = await advance_limit_for(db, user, period=period)
    return MyAdvancesOut(
        period=period,
        rows=[
            MyAdvanceRow(
                id=r.id,
                amount=float(r.amount),
                status=r.status,
                reason=r.reason,
                issued_on=r.issued_on,
                created_at=r.created_at,
            )
            for r in rows
        ],
        # Rad etilgani JAMIGA kirmaydi — u pul emas.
        total=sum(
            float(r.amount)
            for r in rows
            if r.status != PayrollAdjustmentStatus.rejected.value
        ),
        remaining_limit=info.limit,
        limit_reason=info.reason,
    )


@router.get(
    "/my/{telegram_id}/advances",
    response_model=MyAdvancesOut,
    dependencies=[Depends(verify_bot_secret)],
)
async def my_advances_bot(telegram_id: int, db: AsyncSession = Depends(get_db)) -> MyAdvancesOut:
    """Bot uchun. Shaxs `telegram_id` dan yechiladi — boshqa xodimning
    avansini so'rash imkoni yo'q (path'da user_id umuman yo'q)."""
    user = await db.scalar(select(User).where(User.telegram_id == telegram_id))
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Foydalanuvchi topilmadi")
    return await _my_advances(db, user)


@router.get("/me/advances", response_model=MyAdvancesOut)
async def my_advances_web(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> MyAdvancesOut:
    """Kabinet (JWT) versiyasi — shaxs TOKENDAN olinadi."""
    return await _my_advances(db, user)


@router.get("/my/{telegram_id}", response_model=BotPayslipOut, dependencies=[Depends(verify_bot_secret)])
async def my_payslip(telegram_id: int, db: AsyncSession = Depends(get_db)) -> BotPayslipOut:
    """Bot uchun — shaxsni `telegram_id`dan yechadi, mantiq yordamchida."""
    user = await db.scalar(select(User).where(User.telegram_id == telegram_id))
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Foydalanuvchi topilmadi")
    return await _latest_payslip_for_user(db, user)


@router.get("/me/payslip", response_model=BotPayslipOut)
async def my_payslip_web(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> BotPayslipOut:
    """Web (JWT) versiyasi — xodim kabineti uchun. Shaxs TOKENDAN olinadi
    (path'da user_id yo'q — xodim boshqa birovning oyligini so'ray olmasligi
    uchun). Yo'l ataylab `/me/payslip`: bot varianti `/my/{telegram_id}` —
    ikkisi turli segment sonida, to'qnashmaydi."""
    return await _latest_payslip_for_user(db, user)


@router.get(
    "/my/{telegram_id}/late-status", response_model=BotLateStatusOut, dependencies=[Depends(verify_bot_secret)]
)
async def my_late_status(telegram_id: int, db: AsyncSession = Depends(get_db)) -> BotLateStatusOut:
    user = await db.scalar(select(User).where(User.telegram_id == telegram_id))
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Foydalanuvchi topilmadi")
    return await _late_status_for_user(db, user)


@router.get("/me/late-status", response_model=BotLateStatusOut)
async def my_late_status_web(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> BotLateStatusOut:
    """Web (JWT) versiyasi — CheckIn.tsx uchun. Xodim faqat O'ZINING holatini
    ko'radi (path'da user_id yo'q, tokendan olinadi)."""
    return await _late_status_for_user(db, user)
