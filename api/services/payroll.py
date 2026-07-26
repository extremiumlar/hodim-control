"""Oylik ish haqi + kechikish jarimasi + qo'shimcha ish — hisoblash yadrosi.

Spetsifikatsiya: OYLIK_JARIMA_REJASI.md (2-4-bo'lim) + 9-bo'limdagi HR
qarorlari (2026-07-27). Bosqich 0/1 ustiga quriladi: `Attendance` (kechikish/
ishlangan vaqt allaqachon hisoblangan), `WorkScheduleWeekly/Override`
(rejadagi ish oynasi), `ExcusedDay` (sababli kun), `Bonus` (KPI bonusi).

Muhim qoidalar:
- Jarima faqat `status='late'` (ya'ni ish kuni, sababli EMAS) kunlar bo'yicha.
- Limit DAQIQADA, xronologik yeyiladi: chegaradan o'tkazgan kunning o'zi hali
  bepul, undan keyingi HAR bir kechikkan kun jarimali (9-bo'lim, savol 1).
- `resolve_policy`: xodim > lavozim > global — faqat FAOL (`is_active`) qator
  ishtirok etadi; bir daraja faol qatorsiz bo'lsa, KEYINGI (kengroq) darajaga
  o'tiladi.
- Hech qanday `FinePolicy` topilmasa — jarima UMUMAN hisoblanmaydi (0).
  Bosqich 1'da ataylab seed qilinmagan: HR birinchi qoidani o'zi yaratishi shart.
- Barcha summalar `Decimal` (Numeric ustunlar SQLAlchemy'dan shunday qaytadi);
  yaxlitlash faqat OXIRIDA (`round_money`, default 100 so'mgacha).
- `run_payroll` IDEMPOTENT: qayta chaqirilsa eski `PayslipItem`lar o'chirilib,
  bir xil natija bilan qayta yoziladi — dublikat yo'q.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.routers.hourly_plan import DEFAULT_END, DEFAULT_START
from api.timeutil import work_minutes
from db.models import (
    AbsentMode,
    Attendance,
    Bonus,
    ExcusedDay,
    ExcusedStatus,
    FineMode,
    FinePolicy,
    NormHoursSource,
    OvertimeEntry,
    OvertimeEntryStatus,
    OvertimeMode,
    OvertimeProfile,
    PayBasis,
    PayrollAdjustment,
    PayrollAdjustmentKind,
    PayrollPeriod,
    PayrollPeriodStatus,
    Payslip,
    PayslipItem,
    PayslipStatus,
    Role,
    SalaryRate,
    User,
    WorkScheduleOverride,
    WorkScheduleWeekly,
)

# Davomat bilan bir xil qamrov (ATTENDANCE_TRACKED_ROLES) — Boshliqdan tashqari
# hamma. Payroll fuqarosi bo'lish uchun davomat kuzatuvi kerak (jarima/soatbay
# shundan hisoblanadi); Boshliq uchun alohida oylik jarayon YO'Q (hozircha).
PAYROLL_TRACKED_ROLES = tuple(r.value for r in Role if r is not Role.boss)

# Oxirgi yaxlitlash bosqichi — faqat `gross`/`net` ga qo'llanadi, oraliq
# summalar (satrlar) to'liq aniqlik bilan saqlanadi.
PAYROLL_ROUND_TO = 100


class PayrollLocked(Exception):
    """Davr qulflangan (`PayrollPeriod.locked=True`) — qayta hisoblash rad etildi."""


def _hm_to_min(hm: str) -> int:
    h, m = hm.split(":")
    return int(h) * 60 + int(m)


def _period_bounds(period: str) -> tuple[date, date]:
    """"YYYY-MM" -> [oy boshi, keyingi oy boshi) — `Bonus`/`calculate_bonus`
    bilan bir xil qoida."""
    year, month = (int(p) for p in period.split("-"))
    start = date(year, month, 1)
    end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return start, end


def round_money(amount: Decimal, nearest: int = PAYROLL_ROUND_TO) -> Decimal:
    if nearest <= 0:
        return amount
    step = Decimal(nearest)
    return (amount / step).to_integral_value(rounding=ROUND_HALF_UP) * step


def _dec(value) -> Decimal:
    """Numeric ustunlardan kelgan qiymatni (Decimal/float/None) xavfsiz
    Decimal'ga o'giradi; `None` -> 0."""
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


# ─────────────────────────────────────────────────────────────────
# Qoida/stavka aniqlash (resolve)
# ─────────────────────────────────────────────────────────────────


async def resolve_policy(db: AsyncSession, user: User) -> FinePolicy | None:
    """Jarima qoidasi — 3 DARAJALI: xodim > lavozim > global. Faqat FAOL
    (`is_active=True`) qator ishtirok etadi — bir daraja faol qatorsiz bo'lsa
    (yo'q yoki o'chirilgan), keyingi (kengroq) darajaga o'tiladi. Hech qanday
    faol qoida topilmasa `None` — chaqiruvchi buni "jarima yo'q" deb talqin
    qiladi (Bosqich 1da ataylab seed qilinmagan)."""
    user_policy = await db.scalar(
        select(FinePolicy).where(
            FinePolicy.scope == "user",
            FinePolicy.scope_id == user.id,
            FinePolicy.is_active.is_(True),
        )
    )
    if user_policy is not None:
        return user_policy

    if user.position_id is not None:
        position_policy = await db.scalar(
            select(FinePolicy).where(
                FinePolicy.scope == "position",
                FinePolicy.scope_id == user.position_id,
                FinePolicy.is_active.is_(True),
            )
        )
        if position_policy is not None:
            return position_policy

    return await db.scalar(
        select(FinePolicy).where(FinePolicy.scope == "global", FinePolicy.is_active.is_(True))
    )


async def resolve_rate(db: AsyncSession, user_id: int, on_date: date) -> SalaryRate | None:
    """Amaldagi oylik stavka: `effective_from <= on_date` bo'yicha eng
    so'nggisi (`Norm`dagi bilan bir xil "tarixiy versiya" naqshi). Yumshoq
    o'chirilgan (Bosqich 3.5, Dasturchi rejimi) yozuvlar chetlab o'tiladi."""
    return await db.scalar(
        select(SalaryRate)
        .where(
            SalaryRate.user_id == user_id,
            SalaryRate.effective_from <= on_date,
            SalaryRate.deleted_at.is_(None),
        )
        .order_by(SalaryRate.effective_from.desc())
        .limit(1)
    )


async def _first_rate(db: AsyncSession, user_id: int) -> SalaryRate | None:
    return await db.scalar(
        select(SalaryRate)
        .where(SalaryRate.user_id == user_id, SalaryRate.deleted_at.is_(None))
        .order_by(SalaryRate.effective_from.asc())
        .limit(1)
    )


# ─────────────────────────────────────────────────────────────────
# Kunma-kun ma'lumot yig'ish
# ─────────────────────────────────────────────────────────────────


async def month_schedule(db: AsyncSession, user: User, period: str) -> list[dict]:
    """Berilgan oy uchun har kunlik amaldagi ish oynasi (override > haftalik >
    default, `hourly_plan._effective_today` bilan BIR XIL qoida) — BITTA
    so'rovda override va weekly olinib, kunlar Pythonda hisoblanadi (N+1
    o'rniga; oyiga 30 kun × har bir xodim uchun 60 so'rov emas)."""
    period_start, period_end = _period_bounds(period)

    overrides = {
        o.date: o
        for o in await db.scalars(
            select(WorkScheduleOverride).where(
                WorkScheduleOverride.user_id == user.id,
                WorkScheduleOverride.date >= period_start,
                WorkScheduleOverride.date < period_end,
            )
        )
    }
    weekly = {
        w.weekday: w
        for w in await db.scalars(
            select(WorkScheduleWeekly).where(WorkScheduleWeekly.user_id == user.id)
        )
    }

    days: list[dict] = []
    d = period_start
    while d < period_end:
        ov = overrides.get(d)
        if ov is not None:
            is_working = ov.is_working
            start, end = (ov.start_time or DEFAULT_START, ov.end_time or DEFAULT_END) if is_working else ("", "")
        else:
            w = weekly.get(d.weekday())
            if w is not None:
                is_working = w.is_working
                start, end = (w.start_time or DEFAULT_START, w.end_time or DEFAULT_END) if is_working else ("", "")
            else:
                is_working = d.weekday() < 5
                start, end = (DEFAULT_START, DEFAULT_END) if is_working else ("", "")
        minutes = work_minutes(_hm_to_min(start), _hm_to_min(end)) if is_working else 0
        days.append(
            {"date": d, "is_working": is_working, "start": start, "end": end, "scheduled_minutes": minutes}
        )
        d = date.fromordinal(d.toordinal() + 1)
    return days


async def collect_attendance(db: AsyncSession, user: User, period: str) -> list[dict]:
    """Oy davomidagi har kun uchun: reja (ish oynasi) + haqiqiy `Attendance` +
    sababli (`ExcusedDay` tasdiqlangan) belgisi — YAGONA kunma-kun ro'yxat,
    keyingi barcha `compute_*` funksiyalari shundan foydalanadi.

    `excused` ikki manbadan aniqlanadi (ikkalasi ham tekshiriladi — bittasiga
    tayanish xavfli: check-in oqimi hali har doim ham `status='excused'`
    yozmaydi, faqat qo'lda tuzatish/`recompute_attendance` yozadi):
    (1) mavjud `Attendance.status == 'excused'`, (2) o'sha sanaga tasdiqlangan
    `ExcusedDay` — yozuv umuman yo'q bo'lsa ham (xodim kelmagan, lekin ruxsatli)."""
    period_start, period_end = _period_bounds(period)
    schedule = await month_schedule(db, user, period)

    att_by_date = {
        a.date: a
        for a in await db.scalars(
            select(Attendance).where(
                Attendance.user_id == user.id,
                Attendance.date >= period_start,
                Attendance.date < period_end,
            )
        )
    }
    excused_dates = {
        e.date
        for e in await db.scalars(
            select(ExcusedDay).where(
                ExcusedDay.user_id == user.id,
                ExcusedDay.date >= period_start,
                ExcusedDay.date < period_end,
                ExcusedDay.status == ExcusedStatus.approved.value,
            )
        )
    }

    days: list[dict] = []
    for row in schedule:
        d = row["date"]
        att = att_by_date.get(d)
        excused = (att is not None and att.status == "excused") or d in excused_dates

        if not row["is_working"]:
            status = "weekend"
        elif excused:
            status = "excused"
        elif att is None:
            # Kutilgan holatda evening-job (`write_absent_records`) bu kunga
            # allaqachon 'absent' yozgan bo'lishi kerak — bu shox faqat himoya
            # (job o'tkazib yuborgan/hali ishlamagan hollar uchun).
            status = "absent"
        else:
            status = att.status

        days.append(
            {
                **row,
                "attendance": att,
                "excused": excused,
                "status": status,
                "late_minutes": att.late_minutes if att else 0,
                "worked_minutes": att.worked_minutes if att else 0,
            }
        )
    return days


# ─────────────────────────────────────────────────────────────────
# Hisoblash — toza funksiyalar (DB'siz)
# ─────────────────────────────────────────────────────────────────


def compute_late_fine(days: list[dict], policy: FinePolicy | None) -> dict:
    """Kechikish jarimasi. QAROR (9-bo'lim, savol 1-2): bepul limit
    DAQIQADA (`free_late_minutes_per_month`); limit tugagach — undan keyingi
    HAR bir kechikkan KUNGA qat'iy summa (`fine_per_day`, kechikish necha
    daqiqa bo'lishidan qat'i nazar). Limit XRONOLOGIK yeyiladi: chegaradan
    o'tkazgan kunning o'zi hali bepul (`cumulative_before < limit`), undan
    keyingi kun(lar) jarimali.

    `free_late_minutes_per_month` berilmagan (`None`) bo'lsa 0 deb olinadi —
    "limit sozlanmagan" xavfsiz tomonga (jarima ertaroq boshlanadi) og'adi,
    aksincha emas."""
    late_days = [d for d in days if d["status"] == "late" and not d["excused"]]
    result = {
        "late_days": len(late_days),
        "late_minutes": sum(d["late_minutes"] for d in late_days),
        "fined_days": 0,
        "fined_minutes": 0,
        "amount": Decimal("0"),
        "detail": [],
    }
    if policy is None or policy.fine_mode != FineMode.per_day.value:
        # ⭐ per_minute/tiered/percent_of_daily — kelajakda; hozircha faqat
        # per_day qo'llab-quvvatlanadi (9-bo'lim QAROR).
        return result

    free_limit = policy.free_late_minutes_per_month or 0
    fine_per_day = _dec(policy.fine_per_day)

    cumulative = 0
    for d in late_days:  # `days` sana bo'yicha o'sish tartibida — xronologik
        before = cumulative
        cumulative += d["late_minutes"]
        fined = before >= free_limit
        amount = fine_per_day if fined else Decimal("0")
        if fined:
            result["fined_days"] += 1
            result["fined_minutes"] += d["late_minutes"]
            result["amount"] += amount
        result["detail"].append(
            {
                "date": d["date"].isoformat(),
                "late_minutes": d["late_minutes"],
                "cumulative_before": before,
                "fined": fined,
                "amount": float(amount),
            }
        )
    return result


def compute_absent_fine(days: list[dict], policy: FinePolicy | None) -> dict:
    """Kelmagan kun jarimasi. QAROR (9-bo'lim, savol 5): kunlik ish haqi
    ulushi EMAS — `absent_mode='fixed'` bo'lsa HR kiritgan qat'iy summa
    (`absent_fine`) har kelmagan kunga. `deduct_daily` — ⭐ kelajakda (hozir
    qo'llanmaydi, `compute_base` allaqachon faqat ishlangan/rejadagi kunlarni
    hisobga oladi)."""
    absent_days = [d for d in days if d["status"] == "absent"]
    result = {"absent_days": len(absent_days), "amount": Decimal("0")}
    if policy is None or policy.absent_mode != AbsentMode.fixed.value:
        return result
    fine = _dec(policy.absent_fine)
    result["amount"] = fine * len(absent_days)
    return result


def apply_fine_cap(late_amount: Decimal, absent_amount: Decimal, base_amount: Decimal, policy: FinePolicy | None):
    """Oylik jarima chegarasi (9-bo'lim, savol 4, MAJBURIY) — `late` va
    `absent` jarimasining JAMI summasiga qo'llanadi (ikkalasi ham "jarima").
    Ikkala cap turi (`monthly_cap_amount`, `monthly_cap_percent`) sozlangan
    bo'lsa — QATTIQROQ (kichikroq) cheklov g'olib chiqadi.

    Cap oshib ketsa — ikkala jarima turi bir xil NISBATDA qisqartiriladi
    (biri butunlay yo'q qilinib, ikkinchisi to'liq qolib ketmasin)."""
    raw_total = late_amount + absent_amount
    if policy is None or raw_total <= 0:
        return late_amount, absent_amount, raw_total, False

    caps: list[Decimal] = []
    if policy.monthly_cap_amount is not None:
        caps.append(_dec(policy.monthly_cap_amount))
    if policy.monthly_cap_percent is not None and base_amount > 0:
        caps.append(base_amount * _dec(policy.monthly_cap_percent) / Decimal(100))

    if not caps:
        # HR cap kiritmagan — bu holat API/validatsiya darajasida (Bosqich 3)
        # ushlanishi kerak (cap MAJBURIY maydon). Servis darajasida cheklovsiz
        # qoldiramiz — aks holda sukut bo'yicha cheksiz jarima o'tkazib yuborish
        # ham noto'g'ri bo'lardi.
        return late_amount, absent_amount, raw_total, False

    cap = min(caps)
    if raw_total <= cap:
        return late_amount, absent_amount, raw_total, False

    ratio = cap / raw_total
    return late_amount * ratio, absent_amount * ratio, raw_total, True


def compute_base(rate, first_rate, days: list[dict], period_start: date) -> tuple[Decimal, dict | None]:
    """Asosiy oylik. `pay_basis` bo'yicha:
    - `monthly` — qat'iy stavka, lekin PRORATA: agar xodimning birinchi
      stavkasi (`first_rate.effective_from`) shu oyning o'rtasida boshlansa,
      faqat o'sha kundan keyingi rejadagi ish kunlari ulushi to'lanadi
      (⭐ band: oy oxirida ishdan bo'shash uchun alohida sana maydoni
      hozircha YO'Q — faqat BOSHLANISH tomoni proratalanadi).
    - `daily`/`hourly` — o'z-o'zidan proratalanadi (faqat haqiqiy
      ishlangan kun/daqiqa bo'yicha hisoblanadi)."""
    if rate is None:
        return Decimal("0"), None
    amount = _dec(rate.amount)
    basis = rate.pay_basis

    if basis == PayBasis.hourly.value:
        worked_minutes = sum(d["worked_minutes"] for d in days if d["status"] in ("present", "late"))
        hours = Decimal(worked_minutes) / Decimal(60)
        base = amount * hours
        item = {
            "kind": "base",
            "label": f"Soatbay — {hours:.1f} soat",
            "quantity": hours,
            "rate": amount,
            "amount": base,
        }
        return base, item

    if basis == PayBasis.daily.value:
        worked_days = sum(1 for d in days if d["status"] in ("present", "late"))
        base = amount * Decimal(worked_days)
        item = {
            "kind": "base",
            "label": f"Kunbay — {worked_days} kun",
            "quantity": Decimal(worked_days),
            "rate": amount,
            "amount": base,
        }
        return base, item

    # monthly (default)
    full_scheduled = sum(1 for d in days if d["is_working"])
    effective_from = first_rate.effective_from if first_rate is not None else period_start
    prorate_from = max(period_start, effective_from)
    prorated_scheduled = sum(1 for d in days if d["is_working"] and d["date"] >= prorate_from)

    if full_scheduled == 0:
        base = Decimal("0")
        label = "Asosiy oylik"
    elif prorated_scheduled >= full_scheduled:
        base = amount
        label = "Asosiy oylik"
    else:
        ratio = Decimal(prorated_scheduled) / Decimal(full_scheduled)
        base = amount * ratio
        label = f"Asosiy oylik (prorata — {prorated_scheduled}/{full_scheduled} kun)"

    item = {"kind": "base", "label": label, "quantity": None, "rate": amount, "amount": base}
    return base, item


# ─────────────────────────────────────────────────────────────────
# Qo'shimcha ish — DB kerak (stavka + tasdiqlangan yozuvlar)
# ─────────────────────────────────────────────────────────────────


async def compute_overtime(
    db: AsyncSession, user: User, period: str, profile: OvertimeProfile | None, days: list[dict]
) -> dict:
    """Qo'shimcha ish summasi. Faqat `status='approved'` `OvertimeEntry`
    yozuvlari hisobga olinadi — tasdiqsiz pul hisoblanmaydi (1.3-band).

    `derived` rejimda soatlik stavka = oylik ÷ norma soat (QAROR: norma soati
    ish jadvalidan avtomatik, ya'ni shu oy uchun `days`dagi jami
    `scheduled_minutes`) × `profile.multiplier` (MAJBURIY, tizim darajasida
    default YO'Q — 9-bo'lim, savol 6)."""
    result: dict = {"minutes": 0, "amount": Decimal("0"), "rate_snapshot": None, "detail": []}
    if profile is None or not profile.enabled:
        return result

    period_start, period_end = _period_bounds(period)
    entries = list(
        await db.scalars(
            select(OvertimeEntry)
            .where(
                OvertimeEntry.user_id == user.id,
                OvertimeEntry.date >= period_start,
                OvertimeEntry.date < period_end,
                OvertimeEntry.status == OvertimeEntryStatus.approved.value,
            )
            .order_by(OvertimeEntry.date)
        )
    )

    total_minutes = 0
    for e in entries:
        if e.minutes < profile.min_minutes:
            continue  # himoya — yaratish/tasdiqlashda ham tekshirilishi kerak
        minutes = e.minutes
        if profile.daily_cap_minutes is not None:
            minutes = min(minutes, profile.daily_cap_minutes)
        total_minutes += minutes
        result["detail"].append({"date": e.date.isoformat(), "minutes": minutes, "source": e.source})

    if profile.monthly_cap_minutes is not None:
        total_minutes = min(total_minutes, profile.monthly_cap_minutes)
    result["minutes"] = total_minutes
    if total_minutes <= 0:
        return result

    if profile.mode == OvertimeMode.fixed_rate.value:
        hourly_rate = _dec(profile.fixed_rate_per_hour)
    else:
        if profile.multiplier is None:
            # Profil to'liq sozlanmagan (majburiy maydon, Bosqich 3
            # validatsiyasi ushlashi kerak) — himoya: qo'shimcha ish 0 so'm,
            # noto'g'ri katta summa hisoblanib ketmasin.
            hourly_rate = Decimal("0")
        else:
            rate = await resolve_rate(db, user.id, period_start)
            monthly_amount = _dec(rate.amount) if rate is not None else Decimal("0")
            if profile.norm_hours_source == NormHoursSource.fixed.value and profile.fixed_norm_hours_per_month:
                norm_hours = Decimal(profile.fixed_norm_hours_per_month)
            else:
                scheduled_minutes = sum(d["scheduled_minutes"] for d in days)
                norm_hours = Decimal(scheduled_minutes) / Decimal(60)
            hourly_rate = (monthly_amount / norm_hours * _dec(profile.multiplier)) if norm_hours > 0 else Decimal("0")

    result["rate_snapshot"] = hourly_rate
    result["amount"] = hourly_rate * (Decimal(total_minutes) / Decimal(60))
    return result


# ─────────────────────────────────────────────────────────────────
# Orkestrator
# ─────────────────────────────────────────────────────────────────


def _day_snapshot(d: dict) -> dict:
    return {
        "date": d["date"].isoformat(),
        "is_working": d["is_working"],
        "status": d["status"],
        "late_minutes": d["late_minutes"],
        "worked_minutes": d["worked_minutes"],
        "excused": d["excused"],
    }


def _policy_snapshot(policy: FinePolicy | None) -> dict | None:
    if policy is None:
        return None
    return {
        "id": policy.id,
        "scope": policy.scope,
        "scope_id": policy.scope_id,
        "free_late_minutes_per_month": policy.free_late_minutes_per_month,
        "fine_mode": policy.fine_mode,
        "fine_per_day": float(policy.fine_per_day) if policy.fine_per_day is not None else None,
        "absent_mode": policy.absent_mode,
        "absent_fine": float(policy.absent_fine) if policy.absent_fine is not None else None,
        "monthly_cap_percent": float(policy.monthly_cap_percent) if policy.monthly_cap_percent is not None else None,
        "monthly_cap_amount": float(policy.monthly_cap_amount) if policy.monthly_cap_amount is not None else None,
        "fine_applies_to": policy.fine_applies_to,
    }


def _profile_snapshot(profile: OvertimeProfile | None) -> dict | None:
    if profile is None:
        return None
    return {
        "enabled": profile.enabled,
        "mode": profile.mode,
        "multiplier": float(profile.multiplier) if profile.multiplier is not None else None,
        "fixed_rate_per_hour": float(profile.fixed_rate_per_hour) if profile.fixed_rate_per_hour is not None else None,
        "norm_hours_source": profile.norm_hours_source,
    }


async def build_payslip(db: AsyncSession, user: User, period: str) -> dict:
    """Bitta xodim uchun to'liq hisob — hali DB'ga yozilmagan sof natija:
    `{"fields": {...Payslip ustunlari...}, "items": [...PayslipItem...]}`.
    `run_payroll` buni chaqirib upsert qiladi."""
    period_start, _period_end = _period_bounds(period)
    days = await collect_attendance(db, user, period)
    policy = await resolve_policy(db, user)
    rate = await resolve_rate(db, user.id, period_start)
    first_rate = await _first_rate(db, user.id)
    overtime_profile = await db.scalar(select(OvertimeProfile).where(OvertimeProfile.user_id == user.id))

    base_amount, base_item = compute_base(rate, first_rate, days, period_start)
    late = compute_late_fine(days, policy)
    absent = compute_absent_fine(days, policy)
    late_fine, absent_fine, raw_fine_total, cap_applied = apply_fine_cap(
        late["amount"], absent["amount"], base_amount, policy
    )

    overtime = await compute_overtime(db, user, period, overtime_profile, days)

    bonus_row = await db.scalar(select(Bonus).where(Bonus.user_id == user.id, Bonus.period == period))
    bonus_amount = _dec(bonus_row.amount) if bonus_row is not None else Decimal("0")

    adjustments = list(
        await db.scalars(
            select(PayrollAdjustment).where(PayrollAdjustment.user_id == user.id, PayrollAdjustment.period == period)
        )
    )
    adj_plus = sum((_dec(a.amount) for a in adjustments if a.kind == PayrollAdjustmentKind.plus.value), Decimal("0"))
    adj_minus = sum((_dec(a.amount) for a in adjustments if a.kind == PayrollAdjustmentKind.minus.value), Decimal("0"))

    gross = round_money(base_amount + overtime["amount"] + bonus_amount + adj_plus)
    # ⭐ MA'LUM CHEKLOV: `fine_applies_to` (bonus_first/net_salary) `net` YAKUNIY
    # summasiga TA'SIR QILMAYDI — matematik jihatdan bonusdan avval yechish yoki
    # to'g'ridan-to'g'ri oylikdan yechish YAKUNIY netto qiymatni o'zgartirmaydi
    # (bonus - jarima = xuddi shu ayirma, qaysi "chelak"dan olinishidan qat'i
    # nazar). Farq faqat QAYSI PayslipItem qatori kamayishida ko'rinadi — bu
    # HR uchun huquqiy/hisobot jihatdan muhim bo'lishi mumkin (8.4-band), lekin
    # hozircha items FAQAT `net_salary` (QAROR — 9-bo'lim default) ko'rinishida
    # yig'iladi: jarima alohida "fine_late"/"fine_absent" qatori sifatida.
    # `bonus_first` tanlansa HAM net to'g'ri chiqadi, lekin item-darajasidagi
    # "avval bonusdan yechildi" ko'rinishi hali qurilmagan — Bosqich 3/4da HR
    # shu rejimni tanlasa qo'shiladi.
    net = round_money(base_amount + overtime["amount"] + bonus_amount + adj_plus - late_fine - absent_fine - adj_minus)

    items: list[dict] = []
    if base_item is not None:
        items.append(base_item)
    if overtime["amount"] > 0:
        hrs = Decimal(overtime["minutes"]) / Decimal(60)
        items.append(
            {
                "kind": "overtime",
                "label": f"Qo'shimcha ish — {hrs:.1f} soat",
                "quantity": hrs,
                "rate": overtime["rate_snapshot"],
                "amount": overtime["amount"],
            }
        )
    if bonus_amount > 0:
        items.append({"kind": "bonus", "label": "Bonus (KPI)", "quantity": None, "rate": None, "amount": bonus_amount})
    if late_fine > 0:
        items.append(
            {
                "kind": "fine_late",
                "label": f"Kechikish jarimasi — {late['fined_days']} kun",
                "quantity": Decimal(late["fined_days"]),
                "rate": _dec(policy.fine_per_day) if policy and policy.fine_per_day is not None else None,
                "amount": -late_fine,
            }
        )
    if absent_fine > 0:
        items.append(
            {
                "kind": "fine_absent",
                "label": f"Kelmagan kun — {absent['absent_days']} kun",
                "quantity": Decimal(absent["absent_days"]),
                "rate": _dec(policy.absent_fine) if policy and policy.absent_fine is not None else None,
                "amount": -absent_fine,
            }
        )
    for a in adjustments:
        sign = 1 if a.kind == PayrollAdjustmentKind.plus.value else -1
        items.append(
            {
                "kind": f"adjustment_{a.kind}",
                "label": a.reason,
                "quantity": None,
                "rate": None,
                "amount": sign * _dec(a.amount),
            }
        )

    breakdown = {
        "policy": _policy_snapshot(policy),
        "overtime_profile": _profile_snapshot(overtime_profile),
        "rate_id": rate.id if rate is not None else None,
        "fine_applies_to": policy.fine_applies_to if policy else None,
        "cap_applied": cap_applied,
        "raw_fine_total": float(raw_fine_total),
        "days": [_day_snapshot(d) for d in days],
        "late_detail": late["detail"],
    }

    fields = {
        "base_amount": float(base_amount),
        "pay_basis": rate.pay_basis if rate is not None else PayBasis.monthly.value,
        "rate_snapshot": float(rate.amount) if rate is not None else None,
        "scheduled_days": sum(1 for d in days if d["is_working"]),
        "worked_days": sum(1 for d in days if d["status"] in ("present", "late")),
        "absent_days": absent["absent_days"],
        "excused_days": sum(1 for d in days if d["excused"]),
        "scheduled_minutes": sum(d["scheduled_minutes"] for d in days),
        "worked_minutes": sum(d["worked_minutes"] for d in days),
        "late_days": late["late_days"],
        "late_minutes": late["late_minutes"],
        "fined_late_days": late["fined_days"],
        "fined_late_minutes": late["fined_minutes"],
        "fine_amount": float(late_fine),
        "absent_deduction": float(absent_fine),
        "overtime_minutes": overtime["minutes"],
        "overtime_amount": float(overtime["amount"]),
        "overtime_rate_snapshot": float(overtime["rate_snapshot"]) if overtime["rate_snapshot"] is not None else None,
        "bonus_amount": float(bonus_amount),
        "adjustments_plus": float(adj_plus),
        "adjustments_minus": float(adj_minus),
        "gross": float(gross),
        "net": float(net),
        "currency": "UZS",
        "breakdown": breakdown,
    }
    return {"fields": fields, "items": items}


async def run_payroll(db: AsyncSession, period: str, user_ids: list[int] | None = None) -> dict:
    """Berilgan oy uchun (yoki faqat `user_ids`) barcha xodimlarning
    payslip'ini hisoblab, upsert qiladi. IDEMPOTENT: mavjud `Payslip` topilsa
    ustunlar yangilanadi, eski `PayslipItem`lar o'chirilib qayta yoziladi —
    qayta-qayta chaqirilsa dublikat paydo bo'lmaydi.

    `PayrollPeriod.locked=True` bo'lsa — `PayrollLocked` ko'tariladi (avval
    Dasturchi `reopen` qilishi kerak, Bosqich 3.5)."""
    period_row = await db.scalar(select(PayrollPeriod).where(PayrollPeriod.period == period))
    if period_row is not None and period_row.locked:
        raise PayrollLocked(f"«{period}» davri qulflangan — avval qulfni ochish kerak")
    if period_row is None:
        period_row = PayrollPeriod(period=period, status=PayrollPeriodStatus.draft.value)
        db.add(period_row)
        await db.flush()

    query = select(User).where(User.role.in_(PAYROLL_TRACKED_ROLES), User.is_active.is_(True))
    if user_ids is not None:
        query = query.where(User.id.in_(user_ids))
    users = list(await db.scalars(query))

    calculated = 0
    for user in users:
        result = await build_payslip(db, user, period)
        existing = await db.scalar(select(Payslip).where(Payslip.user_id == user.id, Payslip.period == period))
        now = datetime.utcnow()

        if existing is None:
            payslip = Payslip(
                user_id=user.id, period=period, status=PayslipStatus.calculated.value, calculated_at=now,
                **result["fields"],
            )
            db.add(payslip)
            await db.flush()
        else:
            for key, value in result["fields"].items():
                setattr(existing, key, value)
            existing.status = PayslipStatus.calculated.value
            existing.calculated_at = now
            await db.execute(delete(PayslipItem).where(PayslipItem.payslip_id == existing.id))
            payslip = existing
            await db.flush()

        for i, item in enumerate(result["items"]):
            db.add(
                PayslipItem(
                    payslip_id=payslip.id,
                    kind=item["kind"],
                    label=item["label"],
                    quantity=float(item["quantity"]) if item["quantity"] is not None else None,
                    rate=float(item["rate"]) if item["rate"] is not None else None,
                    amount=float(item["amount"]),
                    sort_order=i,
                )
            )
        calculated += 1

    period_row.status = PayrollPeriodStatus.calculated.value
    period_row.calculated_at = datetime.utcnow()
    await db.commit()
    return {"period": period, "calculated": calculated}
