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

from collections.abc import Awaitable, Callable
from datetime import date, datetime, timezone
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.routers.hourly_plan import DEFAULT_END, DEFAULT_START
from api.timeutil import TASHKENT_TZ, today_local, work_minutes
from db.models import (
    AbsentMode,
    Attendance,
    Bonus,
    ExcusedDay,
    ExcusedStatus,
    FineAppliesTo,
    FineMode,
    FinePolicy,
    FineRemainderMode,
    NormHoursSource,
    OvertimeEntry,
    OvertimeEntryStatus,
    OvertimeMode,
    OvertimeProfile,
    PayBasis,
    PayrollAdjustment,
    PayrollAdjustmentCategory,
    PayrollAdjustmentKind,
    PayrollAdjustmentStatus,
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

# 1.5-band (Shaffoflik): bepul kechikish limitidan shuncha daqiqa (yoki kam)
# qolganda "yaqinlashyapsiz" ogohlantirishi yuboriladi (Bosqich 6).
LATE_WARNING_BUFFER_MINUTES = 15


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


async def load_policy_index(db: AsyncSession) -> dict:
    """Barcha FAOL jarima qoidalarini BITTA so'rovda yuklaydi (§4.3).

    NEGA: `resolve_policy` har xodim uchun 1-3 ta SELECT qilardi. Butun oy
    hisoblanganda bu 20 xodim × 3 = 60 ta ortiqcha so'rov edi, holbuki
    qoidalar jadvali o'nlab qatordan iborat — hammasini bir marta o'qish
    arzonroq.

    `order_by(id)` ATAYLAB: bitta darajada bir nechta faol qator bo'lib
    qolsa (invariant buzilgan holat), qaysi biri tanlanishi TASODIFIY
    bo'lmasin — `resolve_policy` dagi kabi birinchisi olinadi."""
    rows = list(
        await db.scalars(
            select(FinePolicy).where(FinePolicy.is_active.is_(True)).order_by(FinePolicy.id)
        )
    )
    index: dict = {"user": {}, "position": {}, "global": None}
    for row in rows:
        if row.scope == "user" and row.scope_id is not None:
            index["user"].setdefault(row.scope_id, row)
        elif row.scope == "position" and row.scope_id is not None:
            index["position"].setdefault(row.scope_id, row)
        elif row.scope == "global" and index["global"] is None:
            index["global"] = row
    return index


def policy_from_index(index: dict, user: User) -> FinePolicy | None:
    """`resolve_policy` bilan AYNAN bir xil tanlov qoidasi, lekin so'rovsiz."""
    policy = index["user"].get(user.id)
    if policy is not None:
        return policy
    if user.position_id is not None:
        policy = index["position"].get(user.position_id)
        if policy is not None:
            return policy
    return index["global"]


async def resolve_overtime_profile(db: AsyncSession, user_id: int) -> OvertimeProfile | None:
    """Qo'shimcha ish profili — 2 DARAJALI: xodim > global (§3.2).

    NEGA: ilgari profil FAQAT xodim bo'yicha edi va `enabled` default False.
    Ya'ni HR har bir xodimga qo'lda profil ochmaguncha qo'shimcha ish umuman
    hisoblanmasdi — jonli bazada yoqilgan profillar soni 0 edi va shu sababli
    «avtomat hisoblab bersin» talabi bajarilmayotgan edi. Global daraja bilan
    yangi xodim ham o'z-o'zidan qamrab olinadi.

    Xodim qatori TOPILSA — global'ga umuman qaralmaydi, hatto u qator
    `enabled=False` bo'lsa ham: bu «bu xodimga ATAYLAB o'chirilgan» degani
    (aks holda global yoqiq bo'lsa istisnoni yozib bo'lmasdi)."""
    own = await db.scalar(
        select(OvertimeProfile).where(
            OvertimeProfile.user_id == user_id, OvertimeProfile.scope == "user"
        )
    )
    if own is not None:
        return own
    return await db.scalar(select(OvertimeProfile).where(OvertimeProfile.scope == "global"))


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
    # Bayramlar (S-09): umumiy jadvaldan KUCHLI, lekin xodimga atayin
    # qo'yilgan kunlik override'dan kuchsiz — bayram navbatchiligi bo'lishi
    # mumkin va bu qaror HR tomonidan aniq kiritilgan.
    from api.services.holidays import holiday_dates

    bayramlar = await holiday_dates(
        db, period_start, date.fromordinal(period_end.toordinal() - 1)
    )

    days: list[dict] = []
    d = period_start
    while d < period_end:
        ov = overrides.get(d)
        if ov is not None:
            is_working = ov.is_working
            start, end = (ov.start_time or DEFAULT_START, ov.end_time or DEFAULT_END) if is_working else ("", "")
        elif d in bayramlar:
            is_working, start, end = False, "", ""
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
    # `is_paid=False` — «o'z hisobidan» ta'til: kun sababli, lekin haqi
    # to'lanmaydi (`compute_base` monthly stavkadan ayiradi). Sana → to'lovlimi.
    excused_paid_by_date = {
        e.date: e.is_paid
        for e in await db.scalars(
            select(ExcusedDay).where(
                ExcusedDay.user_id == user.id,
                ExcusedDay.date >= period_start,
                ExcusedDay.date < period_end,
                ExcusedDay.status == ExcusedStatus.approved.value,
            )
        )
    }
    excused_dates = set(excused_paid_by_date)

    # HALI KELMAGAN kunlar chegarasi. Oy tugagan bo'lsa `today` oy oxiridan
    # katta bo'ladi va hech bir kun `future` bo'lmaydi — ya'ni yakuniy hisob
    # avvalgidek butun oyni qamrab oladi (regressiya yo'q).
    today = today_local()

    days: list[dict] = []
    for row in schedule:
        d = row["date"]
        att = att_by_date.get(d)
        excused = (att is not None and att.status == "excused") or d in excused_dates

        if not row["is_working"]:
            status = "weekend"
        elif d >= today:
            # ⚠️ ENG MUHIM TUZATISH (2026-08-15). Ilgari bu shox YO'Q edi va
            # kelajakdagi ish kunlari `att is None` sababli 'absent' bo'lardi.
            # Oqibati jonli bazada: 15-avgustda hisoblanganda oyning qolgan
            # yarmi "kelmagan" deb sanalib, kunlik ulush oylikdan ayirilardi —
            # Abdurahmon 3 000 000 o'rniga 115 385 so'm oldi (25 kun "kelmagan").
            #
            # `future` holati BARCHA pul yo'llaridan tashqarida qoladi:
            # `compute_absent_fine` va `compute_base`dagi kelmagan-kun ayirmasi
            # ikkalasi ham `status == "absent"` bo'yicha filtrlaydi.
            #
            # DIQQAT: kunlik ulush maxraji (`full_scheduled`) ATAYIN butun oy
            # bo'yicha qoladi — aks holda bitta kelmagan kun uchun ayirma
            # ~2 barobar oshib ketardi (5 mln / 11 kun ≠ 5 mln / 26 kun).
            #
            # BUGUN HAM shu yerga kiradi (`>=`, `>` emas — 2026-08-17). Sabab:
            # kun hali TUGAMAGAN. HR ertalab soat 10:00 da hisoblasa, hali
            # ishga yetib kelmagan HAMMA xodim «kelmagan» sanalib pul
            # yo'qotardi; kechqurungi `write_absent_records` esa o'sha kunni
            # ancha keyin yopadi. Oy yakunlanganda bu zarar keltirmaydi:
            # avtomatik hisob keyingi oyning 1-kuni ishlaydi, ya'ni `today`
            # davrdan tashqarida bo'lib, oyning oxirgi kuni ham to'liq
            # sanaladi.
            status = "future"
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
                # Faqat `ExcusedDay` yozuvi bor kunlar to'lovsiz bo'lishi
                # mumkin. `Attendance.status == 'excused'` bo'lib yozuvi
                # yo'q kun (qo'lda tuzatish) — avvalgidek to'lovli.
                "excused_paid": excused_paid_by_date.get(d, True),
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
    """Kelmagan kun uchun QAT'IY jarima (`absent_mode='fixed'`).

    IKKI REJIM (egasining 2026-08-08 qarori bilan ikkinchisi yoqildi):
    - `fixed` — HR kiritgan qat'iy summa har kelmagan kunga (bu funksiya);
    - `deduct_daily` — kunlik ish haqi ulushi bazadan ayiriladi
      (`compute_base`), bu yerda 0 qaytariladi, aks holda xodim ikki marta
      jazolanardi.

    ⚠️ Eski izohda "compute_base allaqachon faqat ishlangan kunlarni hisobga
    oladi" deyilgan edi — bu FAQAT `daily`/`hourly` uchun to'g'ri. `monthly`
    stavkada baza kelmagan kundan kamaymasdi, ya'ni `absent_fine=0` bo'lsa
    kelmaslik umuman bepul edi (jonli bazada aynan shunday holat topildi)."""
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


def split_fine(
    total_fine: Decimal,
    bonus_amount: Decimal,
    carried_in: Decimal,
    policy: FinePolicy | None,
) -> dict:
    """Ushlanma QAYERDAN olinishini taqsimlaydi (yangi TZ 2.1 / S-02).

    Kirish:
      `total_fine`  — shu oyning ushlanmasi (cap QO'LLANGANDAN KEYIN);
      `bonus_amount`— shu oy bonusi (to'liq, kamaytirilmagan);
      `carried_in`  — o'tgan oydan ko'chib kelgan qoldiq (`carry_next_month`).

    Chiqish: `from_bonus`, `from_salary`, `carried_out`, `dropped`.

    QOIDA:
      • `net_salary` — hammasi oylikdan (eski xatti-harakat);
      • `bonus_first` — avval bonusdan, bonus yetmasa qoldiq
        `fine_remainder_mode` bo'yicha:
          `drop`             → umuman ushlanmaydi (DEFAULT, eng xavfsiz);
          `carry_next_month` → keyingi oy bonusiga o'tadi;
          `from_salary`      → oylikdan ushlanadi.

    ⚠️ `carried_in` ATAYLAB bonusdan oldin emas, BIRGA hisoblanadi: o'tgan
    oyning qoldig'i ham, shu oyning ushlanmasi ham bir xil manbadan (bonus)
    olinadi. Aks holda tartib qaysi biri «omadli» bo'lishini hal qilib
    qo'yardi va natija tushuntirib bo'lmas holga kelardi.

    ⚠️ CAP bu funksiyaga KIRMAYDI — u bazadan hisoblanadi va chaqiruvchida
    allaqachon qo'llangan (S-02 «Tuzoq 1»). Bonusdan olish cheklovni
    kengaytirmaydi."""
    nol = Decimal("0")
    yigindi = total_fine + carried_in
    if yigindi <= 0:
        return {"from_bonus": nol, "from_salary": nol, "carried_out": nol, "dropped": nol}

    rejim = policy.fine_applies_to if policy is not None else FineAppliesTo.net_salary.value
    if rejim != FineAppliesTo.bonus_first.value:
        return {"from_bonus": nol, "from_salary": yigindi, "carried_out": nol, "dropped": nol}

    from_bonus = min(bonus_amount, yigindi) if bonus_amount > 0 else nol
    qoldiq = yigindi - from_bonus
    if qoldiq <= 0:
        return {"from_bonus": from_bonus, "from_salary": nol, "carried_out": nol, "dropped": nol}

    qoldiq_rejimi = (
        policy.fine_remainder_mode
        if policy is not None and getattr(policy, "fine_remainder_mode", None)
        else FineRemainderMode.drop.value
    )
    if qoldiq_rejimi == FineRemainderMode.from_salary.value:
        return {"from_bonus": from_bonus, "from_salary": qoldiq, "carried_out": nol, "dropped": nol}
    if qoldiq_rejimi == FineRemainderMode.carry_next_month.value:
        return {"from_bonus": from_bonus, "from_salary": nol, "carried_out": qoldiq, "dropped": nol}
    # `drop` — default va noma'lum qiymat uchun ham (xavfsiz tomon)
    return {"from_bonus": from_bonus, "from_salary": nol, "carried_out": nol, "dropped": qoldiq}


def compute_base(
    rate, first_rate, days: list[dict], period_start: date, policy: FinePolicy | None = None
) -> tuple[Decimal, dict | None, dict | None]:
    """Asosiy oylik. `pay_basis` bo'yicha:
    - `monthly` — qat'iy stavka, lekin PRORATA: agar xodimning birinchi
      stavkasi (`first_rate.effective_from`) shu oyning o'rtasida boshlansa,
      faqat o'sha kundan keyingi rejadagi ish kunlari ulushi to'lanadi
      (⭐ band: oy oxirida ishdan bo'shash uchun alohida sana maydoni
      hozircha YO'Q — faqat BOSHLANISH tomoni proratalanadi).
    - `daily`/`hourly` — o'z-o'zidan proratalanadi (faqat haqiqiy
      ishlangan kun/daqiqa bo'yicha hisoblanadi).

    KELMAGAN KUN (2026-08-08, egasining qarori — "A variant"):
    `policy.absent_mode == 'deduct_daily'` bo'lsa, sababsiz kelmagan har bir
    REJADAGI kun uchun kunlik ulush asosiy oylikdan AYIRILADI va alohida
    qat'iy jarima QO'YILMAYDI (`compute_absent_fine` bunday rejimda 0
    qaytaradi — ikki marta jazolanmasin).

    NEGA JARIMA EMAS, BALKI BAZANING KAMAYISHI: kelmagan kun uchun haq
    to'lanmasligi jazo emas, oddiy hisob. Agar u jarima sifatida yozilsa,
    oylik jarima CHEKLOVIGA (`monthly_cap_percent`, odatda 20%) tushib
    qolardi — ya'ni oyning yarmida kelmagan xodim baribir oylikning 80% ini
    olardi. Bazadan ayirilgani uchun cheklov unga tegmaydi.

    Sababli kunlar (`excused`) AYIRILMAYDI — ular tasdiqlangan (kasallik va
    h.k.) va haqi saqlanadi. ISTISNO (2026-08-13): `is_paid=False` bo'lgan
    sababli kun («o'z hisobidan» ta'til) monthly stavkadan AYIRILADI —
    kelmagan kun bilan bir xil kunlik ulush bo'yicha. Ilgari bunday farq
    yo'q edi va oyliklilarga o'z hisobidan ta'til bepul dam bo'lib qolardi
    (daily/hourly da esa sababli kun hech qachon to'lanmaydi — u yerda
    o'zgarish kerak emas).

    Qaytaradi: (summa, asosiy qator, kelmagan-kun ayirmasi | None,
    to'lovsiz-ta'til ayirmasi | None).
    """
    if rate is None:
        return Decimal("0"), None, None, None
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
        # Soatbay allaqachon faqat ISHLANGAN daqiqa bo'yicha — kelmagan kun
        # ham, sababli kun ham o'z-o'zidan to'lanmaydi (ikkalasi `present`/
        # `late` emas), alohida ayirma kerak emas.
        return base, item, None, None

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
        # Kunbay ham o'z-o'zidan proratali.
        return base, item, None, None

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

    # ── To'lovsiz sababli kunlar («o'z hisobidan») ──
    # Kelmagan kundan farqi: bu JAZO EMAS va `policy` ga bog'liq emas —
    # xodim o'zi so'ragan, tizim faqat haq to'lamaydi. Shuning uchun
    # `absent_mode` sozlamasidan mustaqil ishlaydi.
    unpaid_item = None
    if full_scheduled > 0:
        unpaid_days = sum(
            1
            for d in days
            if d["is_working"] and d["status"] == "excused" and not d.get("excused_paid", True)
        )
        if unpaid_days:
            daily_share = base / Decimal(full_scheduled)
            deduction = min(daily_share * Decimal(unpaid_days), base)
            base = base - deduction
            unpaid_item = {
                "kind": "unpaid_leave_deduction",
                "label": f"O'z hisobidan ta'til — {unpaid_days} kun × {round_money(daily_share):,.0f}".replace(",", " "),
                "quantity": Decimal(unpaid_days),
                "rate": round_money(daily_share),
                "amount": -round_money(deduction),
            }
            item["amount"] = base

    # ── Kelmagan kunlar uchun kunlik ulushni ayirish ──
    absent_item = None
    if (
        policy is not None
        and policy.absent_mode == AbsentMode.deduct_daily.value
        and full_scheduled > 0
    ):
        absent_days = sum(1 for d in days if d["is_working"] and d["status"] == "absent")
        if absent_days:
            # Kunlik ulush TO'LIQ stavkadan emas, PRORATA qilingan bazadan
            # olinadi: oy o'rtasida ishga kirgan xodimning kunlik haqi ham
            # o'sha proratali summadan kelib chiqishi kerak.
            daily_share = base / Decimal(full_scheduled)
            deduction = daily_share * Decimal(absent_days)
            # Ayirma bazadan katta bo'lib ketmasin (nazariy: barcha kun
            # kelmagan) — manfiy oylik chiqmasligi kerak.
            deduction = min(deduction, base)
            base = base - deduction
            absent_item = {
                "kind": "absent_deduction",
                "label": f"Kelmagan kunlar — {absent_days} kun × {round_money(daily_share):,.0f}".replace(",", " "),
                "quantity": Decimal(absent_days),
                "rate": round_money(daily_share),
                "amount": -round_money(deduction),
            }
    return base, item, absent_item, unpaid_item


# ─────────────────────────────────────────────────────────────────
# Qo'shimcha ish — DB kerak (stavka + tasdiqlangan yozuvlar)
# ─────────────────────────────────────────────────────────────────


async def compute_overtime(
    db: AsyncSession,
    user: User,
    period: str,
    profile: OvertimeProfile | None,
    days: list[dict],
    rate: SalaryRate | None = None,
) -> dict:
    """Qo'shimcha ish summasi. Faqat `status='approved'` `OvertimeEntry`
    yozuvlari hisobga olinadi — tasdiqsiz pul hisoblanmaydi (1.3-band).

    `derived` rejimda soatlik stavka = oylik ÷ norma soat (QAROR: norma soati
    ish jadvalidan avtomatik, ya'ni shu oy uchun `days`dagi jami
    `scheduled_minutes`) × `profile.multiplier` (MAJBURIY, tizim darajasida
    default YO'Q — 9-bo'lim, savol 6).

    `rate` — chaqiruvchi allaqachon yechgan stavka (`build_payslip` uni
    baza hisobi uchun oladi). Berilmasa shu yerda qayta yechiladi: ilgari
    HAR DOIM shunday edi va bu har xodimga bitta ortiqcha SQL so'rovi
    demakdi (§4.3 «qo'shimcha»)."""
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

    # 2026-08-15: `minutes` endi MANFIY bo'lishi mumkin (kam ishlangan vaqt) —
    # shuning uchun chegara va cheklovlar ABSOLYUT qiymatga, ishora esa
    # saqlanib qoladi. Aks holda `min(minutes, cap)` manfiy qiymatni
    # o'zgarishsiz o'tkazib yuborardi va kunlik cheklov faqat bir tomonga
    # ishlardi.
    total_minutes = 0
    for e in entries:
        if abs(e.minutes) < profile.min_minutes:
            continue  # himoya — yaratish/tasdiqlashda ham tekshirilishi kerak
        minutes = e.minutes
        if profile.daily_cap_minutes is not None:
            ishora = 1 if minutes >= 0 else -1
            minutes = ishora * min(abs(minutes), profile.daily_cap_minutes)
        total_minutes += minutes
        result["detail"].append({"date": e.date.isoformat(), "minutes": minutes, "source": e.source})

    if profile.monthly_cap_minutes is not None:
        ishora = 1 if total_minutes >= 0 else -1
        total_minutes = ishora * min(abs(total_minutes), profile.monthly_cap_minutes)
    result["minutes"] = total_minutes
    if total_minutes == 0:
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
            if rate is None:
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


async def build_payslip(
    db: AsyncSession, user: User, period: str, policy_index: dict | None = None
) -> dict:
    """Bitta xodim uchun to'liq hisob — hali DB'ga yozilmagan sof natija:
    `{"fields": {...Payslip ustunlari...}, "items": [...PayslipItem...]}`.
    `run_payroll` buni chaqirib upsert qiladi.

    `policy_index` — `load_policy_index` natijasi. Berilsa jarima qoidasi
    so'rovsiz aniqlanadi (§4.3); berilmasa avvalgidek DB'dan yechiladi, ya'ni
    bitta xodimni hisoblovchi chaqiruvchilar o'zgarishsiz ishlayveradi."""
    period_start, _period_end = _period_bounds(period)
    days = await collect_attendance(db, user, period)
    policy = (
        policy_from_index(policy_index, user)
        if policy_index is not None
        else await resolve_policy(db, user)
    )
    rate = await resolve_rate(db, user.id, period_start)
    first_rate = await _first_rate(db, user.id)
    overtime_profile = await resolve_overtime_profile(db, user.id)

    base_amount, base_item, absent_deduct_item, unpaid_leave_item = compute_base(
        rate, first_rate, days, period_start, policy
    )
    late = compute_late_fine(days, policy)
    absent = compute_absent_fine(days, policy)
    late_fine, absent_fine, raw_fine_total, cap_applied = apply_fine_cap(
        late["amount"], absent["amount"], base_amount, policy
    )

    overtime = await compute_overtime(db, user, period, overtime_profile, days, rate=rate)

    bonus_row = await db.scalar(select(Bonus).where(Bonus.user_id == user.id, Bonus.period == period))
    bonus_amount = _dec(bonus_row.amount) if bonus_row is not None else Decimal("0")

    # FAQAT `approved` — avans (2026-08-13) Boshliq tasdig'igacha `pending`
    # turadi va oylikka KIRMAYDI; rad etilgani esa hech qachon kirmaydi.
    # Eski yozuvlar migratsiyada `approved` bo'lib qolgan, ya'ni o'tgan
    # oylarning hisobi o'zgarmaydi.
    adjustments = list(
        await db.scalars(
            select(PayrollAdjustment).where(
                PayrollAdjustment.user_id == user.id,
                PayrollAdjustment.period == period,
                PayrollAdjustment.status == PayrollAdjustmentStatus.approved.value,
            )
        )
    )
    adj_plus = sum((_dec(a.amount) for a in adjustments if a.kind == PayrollAdjustmentKind.plus.value), Decimal("0"))
    adj_minus = sum((_dec(a.amount) for a in adjustments if a.kind == PayrollAdjustmentKind.minus.value), Decimal("0"))

    # ── S-02: ushlanma QAYERDAN olinadi ──
    # O'tgan oy `carry_next_month` rejimida qoldiq qoldirgan bo'lsa, u shu
    # oyga ko'chadi. Manba — o'tgan oy payslip'ining `breakdown` i
    # (`PayrollAdjustment` ATAYLAB ishlatilmaydi: u PUL yozuvi, bu esa
    # hisobning oraliq holati).
    #
    # IDEMPOTENT: shu oy qayta-qayta hisoblansa ham har safar O'SHA
    # o'tgan oy qatoridan o'qiydi — qoldiq ikki marta olinmaydi.
    carried_in = Decimal("0")
    if policy is not None and policy.fine_applies_to == FineAppliesTo.bonus_first.value:
        oldingi = previous_period(period_start)
        oldingi_slip = await db.scalar(
            select(Payslip).where(Payslip.user_id == user.id, Payslip.period == oldingi)
        )
        if oldingi_slip is not None and oldingi_slip.breakdown:
            carried_in = _dec(oldingi_slip.breakdown.get("fine_carried_out"))

    taqsim = split_fine(late_fine + absent_fine, bonus_amount, carried_in, policy)
    fine_from_bonus = taqsim["from_bonus"]
    fine_from_salary = taqsim["from_salary"]

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
    # ⚠️ ENDI `fine_applies_to` YAKUNIY summaga TA'SIR QILADI (ilgari qilmasdi).
    # Sabab: `bonus_first` rejimida bonus yetmasa qoldiq `drop` yoki
    # `carry_next_month` bo'lishi mumkin — ya'ni shu oyda UMUMAN ushlanmaydi.
    # Shuning uchun ayirma `late_fine + absent_fine` emas, TAQSIMLANGAN
    # qismlar yig'indisi.
    net = round_money(
        base_amount
        + overtime["amount"]
        + bonus_amount
        + adj_plus
        - fine_from_bonus
        - fine_from_salary
        - adj_minus
    )

    items: list[dict] = []
    if base_item is not None:
        items.append(base_item)
    # Kelmagan kunlar ayirmasi ASOSIY QATORDAN KEYIN — payslip'da "5 000 000"
    # va ostida "− 16 kun × 217 391" ko'rinsin. Bu jarima EMAS, shuning uchun
    # `fine_*` qatorlari bilan aralashmaydi va cheklovga tushmaydi.
    if absent_deduct_item is not None:
        items.append(absent_deduct_item)
    # To'lovsiz («o'z hisobidan») ta'til ayirmasi — kelmagan kun bilan bir
    # xil joyda, lekin alohida qator: xodim payslip'da nega kam olganini
    # aniq ko'rsin (jazo emas, o'zi so'ragan kun).
    if unpaid_leave_item is not None:
        items.append(unpaid_leave_item)
    # `!= 0` — 2026-08-15 dan qiymat MANFIY ham bo'lishi mumkin (oy bo'yicha
    # kam ishlangan vaqt ortiqchasidan ko'p chiqsa). Ilgari `> 0` edi va
    # manfiy natija `net`ni kamaytirsa ham payslip'da QATOR chiqmasdi —
    # xodim summaning qayerdan kelganini ko'ra olmasdi.
    if overtime["amount"] != 0:
        hrs = Decimal(overtime["minutes"]) / Decimal(60)
        ortiqcha = overtime["minutes"] > 0
        items.append(
            {
                "kind": "overtime",
                "label": (
                    f"Qo'shimcha ish — {hrs:.1f} soat"
                    if ortiqcha
                    else f"Kam ishlangan vaqt — {abs(hrs):.1f} soat"
                ),
                "quantity": hrs,
                "rate": overtime["rate_snapshot"],
                "amount": overtime["amount"],
            }
        )
    if bonus_amount > 0:
        items.append({"kind": "bonus", "label": "Bonus (KPI)", "quantity": None, "rate": None, "amount": bonus_amount})
    # ── Ushlanma qatorlari (S-02) ──
    # Manba qator MATNIDA ko'rsatiladi: xodim «pulim qayerdan kesildi»
    # degan savolga payslip'ning o'zidan javob topsin.
    if fine_from_bonus > 0 and fine_from_salary > 0:
        manba = " (bonus va oylikdan)"
    elif fine_from_bonus > 0:
        manba = " (bonusdan)"
    elif fine_from_salary > 0:
        manba = " (oylikdan)"
    else:
        manba = ""

    if late_fine > 0:
        items.append(
            {
                "kind": "fine_late",
                "label": f"Kechikish ushlanmasi — {late['fined_days']} kun{manba}",
                "quantity": Decimal(late["fined_days"]),
                "rate": _dec(policy.fine_per_day) if policy and policy.fine_per_day is not None else None,
                "amount": -late_fine,
            }
        )
    if absent_fine > 0:
        items.append(
            {
                "kind": "fine_absent",
                "label": f"Kelmagan kun ushlanmasi — {absent['absent_days']} kun{manba}",
                "quantity": Decimal(absent["absent_days"]),
                "rate": _dec(policy.absent_fine) if policy and policy.absent_fine is not None else None,
                "amount": -absent_fine,
            }
        )
    # O'tgan oydan ko'chib kelgan qoldiq — ALOHIDA qator, aks holda summa
    # «qayerdan chiqdi» degan savol tug'ilardi.
    if carried_in > 0:
        items.append(
            {
                "kind": "fine_carry_in",
                "label": f"O'tgan oydan qolgan ushlanma{manba}",
                "quantity": None,
                "rate": None,
                "amount": -carried_in,
            }
        )
    # Olinmagan qism — MUSBAT qator. Busiz qatorlar yig'indisi `net` ga teng
    # bo'lmay qolardi (bu invariant testda qo'riqlanadi).
    olinmagan = taqsim["carried_out"] + taqsim["dropped"]
    if olinmagan > 0:
        izoh = (
            "Ushlanma qoldig'i keyingi oyga o'tdi"
            if taqsim["carried_out"] > 0
            else "Ushlanma qoldig'i olinmadi (bonus yetmadi)"
        )
        items.append(
            {
                "kind": "fine_waived",
                "label": izoh,
                "quantity": None,
                "rate": None,
                "amount": olinmagan,
            }
        )
    for a in adjustments:
        sign = 1 if a.kind == PayrollAdjustmentKind.plus.value else -1
        # Avans qatori ATAYLAB «Avans» deb boshlanadi: xodim payslip'ida
        # buni darhol tanishi kerak (aks holda sabab matni ko'rinib, "bu
        # nima?" degan savol tug'ilardi).
        if a.category == PayrollAdjustmentCategory.advance.value:
            label = f"Avans — {a.issued_on.strftime('%d.%m.%Y')}" if a.issued_on else "Avans"
            if a.reason:
                label += f" ({a.reason})"
        else:
            label = a.reason
        items.append(
            {
                "kind": f"adjustment_{a.kind}",
                "label": label,
                "quantity": None,
                "rate": None,
                "amount": sign * _dec(a.amount),
            }
        )

    # ── ORALIQ HISOB belgisi ──
    # Oy tugamagan bo'lsa hisob "hozirgacha" holatini ko'rsatadi: kelajakdagi
    # kunlar `future` (yuqoriga qarang) va ular na jarimaga, na ayirmaga
    # kiradi. Buni AYTMASAK, xodim oy o'rtasida payslip ochib "nega jarimam
    # yo'q / kunlarim kam" deb chalkashadi — shuning uchun UI shu bayroqqa
    # qarab "Oraliq hisob — {sana}gacha" deb yozadi.
    future_days = sum(1 for d in days if d["status"] == "future")
    # ⚠️ `status != "future"` bo'yicha olish NOTO'G'RI edi: kelajakdagi DAM
    # kunlari «weekend» deb belgilanadi (bu tekshiruv `d > today` dan oldin
    # turadi), shuning uchun 15-avgustda ham `counted_through` 30-avgustni
    # ko'rsatib, HR ga «oy deyarli hisoblangan» degan yolg'on taassurot
    # berardi. To'g'ri javob — oddiygina min(bugun, oy oxiri).
    _bugun = today_local()
    counted_through = max((d["date"] for d in days if d["date"] <= _bugun), default=None)
    breakdown = {
        "policy": _policy_snapshot(policy),
        "overtime_profile": _profile_snapshot(overtime_profile),
        "rate_id": rate.id if rate is not None else None,
        "fine_applies_to": policy.fine_applies_to if policy else None,
        # S-02 — ushlanma taqsimoti. `fine_carried_out` KEYINGI oy hisobida
        # o'qiladi (`carried_in`), shuning uchun nomi aniq.
        "fine_remainder_mode": (
            getattr(policy, "fine_remainder_mode", None) if policy else None
        ),
        "fine_from_bonus": float(fine_from_bonus),
        "fine_from_salary": float(fine_from_salary),
        "fine_carried_in": float(carried_in),
        "fine_carried_out": float(taqsim["carried_out"]),
        "fine_dropped": float(taqsim["dropped"]),
        "cap_applied": cap_applied,
        "raw_fine_total": float(raw_fine_total),
        "is_interim": future_days > 0,
        "future_days": future_days,
        "counted_through": counted_through.isoformat() if counted_through else None,
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
        # Kelmagan kun uchun ushlanma — REJIMDAN QAT'I NAZAR shu maydonda:
        # `fixed` da qat'iy jarima, `deduct_daily` da bazadan ayirilgan kunlik
        # ulush. Aks holda hisobotlarda `deduct_daily` rejimi 0 bo'lib
        # ko'rinardi, holbuki pul ushlab qolingan (faqat boshqa "chelak"dan).
        "absent_deduction": float(
            absent_fine if absent_deduct_item is None else -_dec(absent_deduct_item["amount"])
        ),
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


async def run_payroll(
    db: AsyncSession,
    period: str,
    user_ids: list[int] | None = None,
    on_progress: Callable[[int, int], Awaitable[None]] | None = None,
) -> dict:
    """Berilgan oy uchun (yoki faqat `user_ids`) barcha xodimlarning
    payslip'ini hisoblab, upsert qiladi. IDEMPOTENT: mavjud `Payslip` topilsa
    ustunlar yangilanadi, eski `PayslipItem`lar o'chirilib qayta yoziladi —
    qayta-qayta chaqirilsa dublikat paydo bo'lmaydi.

    `PayrollPeriod.locked=True` bo'lsa — `PayrollLocked` ko'tariladi (avval
    Dasturchi `reopen` qilishi kerak, Bosqich 3.5).

    `on_progress(done, total)` — fon rejimi uchun (§4.3): cron har xodimdan
    keyin `payroll_periods.calc_progress` ni yangilaydi, sayt esa buni
    «12/20 xodim» deb ko'rsatadi. Chaqiruvchi COMMIT qilmasligi kerak —
    yarim hisoblangan payslip'lar ko'rinib qolmasin (progress ustuni
    ATAYLAB alohida sessiyada yangilanadi, `payroll_jobs.py` ga qarang)."""
    # Tizim boshlanishidan OLDINGI davr hisoblanmaydi (TZ §5.4 Qadam 3).
    # Ma'lumot o'chirilgan bo'lsa, u davrni hisoblash hamma kunni «kelmagan»
    # deb sanab, ulkan ayirmali soxta payslip yasardi.
    from api.config import settings as _cfg

    if _cfg.payroll_start_period and period < _cfg.payroll_start_period:
        raise PayrollLocked(
            f"«{period}» — tizim boshlanishidan ({_cfg.payroll_start_period}) oldingi davr. "
            "Bu davr ma'lumoti o'chirilgan, shuning uchun hisoblanmaydi."
        )

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

    # Jarima qoidalari BIR MARTA yuklanadi — har xodimga 1-3 so'rov o'rniga
    # butun yurish uchun bitta (§4.3).
    policy_index = await load_policy_index(db)

    calculated = 0
    for user in users:
        result = await build_payslip(db, user, period, policy_index=policy_index)
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
        if on_progress is not None:
            await on_progress(calculated, len(users))

    period_row.status = PayrollPeriodStatus.calculated.value
    period_row.calculated_at = datetime.utcnow()
    await db.commit()
    return {"period": period, "calculated": calculated}


# ─────────────────────────────────────────────────────────────────
# Bosqich 6 — avtomatika (scheduler chaqiradi, api/routers/payroll.py orqali)
# ─────────────────────────────────────────────────────────────────


def previous_period(today: date) -> str:
    """"YYYY-MM" — `today` turgan oydan OLDINGI oy (9-bo'lim, savol 10: oylik
    hisob "keyingi oyning 1-kuni ertalab" ishga tushganda, o'sha payt
    "joriy oy" allaqachon YANGI oy bo'lgani uchun tugagan oyni hisoblash kerak)."""
    year, month = today.year, today.month
    if month == 1:
        return f"{year - 1}-12"
    return f"{year}-{month - 1:02d}"


def _minute_of_day_local(dt_utc: datetime) -> int:
    """Bazadagi naive-UTC vaqtni (masalan `Attendance.check_out_time`) mahalliy
    devor-soatining kun ichidagi daqiqasiga o'giradi (`attendance.py::_to_local`
    + `_minute_of_day` bilan bir xil qoida, faqat shu yerga ko'chirilmagan —
    servis fayllari o'rtasida doiraviy import xavfi past bo'lgani uchun to'g'ridan
    -to'g'ri yozilgan)."""
    local = dt_utc.replace(tzinfo=timezone.utc).astimezone(TASHKENT_TZ)
    return local.hour * 60 + local.minute


async def detect_overtime_candidates(db: AsyncSession, for_date: date) -> list[OvertimeEntry]:
    """1.3-band: check-out rejadagi ish oynasi tugaganidan KEYIN bo'lgan
    kunlarni avtomatik "qo'shimcha ish" NOMZODI (`pending`) sifatida yaratadi —
    faqat `OvertimeProfile.enabled=True` xodimlarga. Tasdiqsiz pul
    hisoblanmaydi (`compute_overtime` faqat `approved` yozuvlarni o'qiydi) —
    bu funksiya faqat NOMZOD yaratadi, HR/rahbar keyin tasdiqlaydi/rad etadi.

    Allaqachon shu kunga yozuv bo'lsa (qo'lda yoki avvalgi ishga tushirishdan)
    tegilmaydi — `UniqueConstraint(user_id, date)` shunday ham himoya qiladi,
    lekin oldindan tekshirish keraksiz IntegrityError'dan qochadi.

    ⭐ MA'LUM CHEKLOV: yarim tundan oshgan (tungi) smenalar hisobga olinmaydi —
    `check_out_time` ertasi kalendar kuniga o'tib ketsa, kun ichidagi daqiqa
    hisобi noto'g'ri (kichik) chiqib, nomzod yaratilmay qoladi. Bu xavfsiz
    tomonga og'adi (nomzod o'tkazib yuboriladi, noto'g'ri katta summa
    yaratilmaydi) — to'liq yechim kelajakka qoldirilgan."""
    # §3.2: qamrov endi GLOBAL profildan ham keladi. Ilgari faqat shaxsiy
    # `enabled=True` qatorlar qaralardi — ya'ni HR har bir xodimga qo'lda
    # profil ochmaguncha nomzod umuman yaratilmasdi (jonli bazada yoqilgan
    # profil 0 ta edi).
    rows = list(await db.scalars(select(OvertimeProfile)))
    global_profile = next((r for r in rows if r.scope == "global"), None)
    own = {r.user_id: r for r in rows if r.scope == "user" and r.user_id is not None}

    tracked = list(
        await db.scalars(
            select(User).where(User.role.in_(PAYROLL_TRACKED_ROLES), User.is_active.is_(True))
        )
    )
    # Xodim qatori bo'lsa u HAL QILADI (hatto o'chiq bo'lsa ham — bu ataylab
    # qo'yilgan istisno); bo'lmasa global qoida qo'llanadi.
    profiles = {}
    for u in tracked:
        profile = own.get(u.id, global_profile)
        if profile is not None and profile.enabled:
            profiles[u.id] = profile
    if not profiles:
        return []

    existing = set(
        await db.scalars(
            select(OvertimeEntry.user_id).where(
                OvertimeEntry.date == for_date, OvertimeEntry.user_id.in_(profiles.keys())
            )
        )
    )
    candidate_ids = [uid for uid in profiles if uid not in existing]
    if not candidate_ids:
        return []

    users = {u.id: u for u in tracked if u.id in candidate_ids}
    atts = {
        a.user_id: a
        for a in await db.scalars(
            select(Attendance).where(Attendance.date == for_date, Attendance.user_id.in_(candidate_ids))
        )
    }

    # Doiraviy importdan qochish uchun mahalliy (boshqa servislar — attendance.py,
    # idle_watch.py, watch_rules.py — ham xuddi shunday qiladi).
    from api.routers.hourly_plan import _effective_today

    created: list[OvertimeEntry] = []
    for user_id in candidate_ids:
        att = atts.get(user_id)
        user = users.get(user_id)
        profile = profiles[user_id]
        if att is None or user is None or att.check_out_time is None or att.status not in ("present", "late"):
            continue
        is_working, start, end = await _effective_today(db, user, for_date)
        if not is_working:
            continue
        # 2026-08-15 (egasining talabi "vaqtini qo'shib ayirib umumiy
        # hisoblab berish"): endi FAQAT kech ketish emas, kunlik SOF farq
        # o'lchanadi — ishlangan vaqt minus rejadagi vaqt.
        #
        # NEGA SHUNDAY YAXSHIROQ: ilgari faqat `check_out - end` qaralardi,
        # ya'ni xodim kech kelib kech ketsa "qo'shimcha ish" deb yozilardi —
        # aslida u kam ishlagan bo'lishi mumkin edi. Endi kechikish ham,
        # erta ketish ham, tushlik ham bitta sonda hisobga olinadi.
        #
        # Manfiy qiymat = KAM ishlangan vaqt. `compute_overtime` uni oy
        # bo'yicha ortiqcha vaqtdan ayiradi.
        scheduled_minutes = work_minutes(_hm_to_min(start), _hm_to_min(end))
        delta_minutes = (att.worked_minutes or 0) - scheduled_minutes
        # `min_minutes` — SEZGIRLIK chegarasi: bir-ikki daqiqalik farq uchun
        # yozuv yaratilmasin (ikkala yo'nalishda ham).
        if abs(delta_minutes) < max(profile.min_minutes, 1):
            continue
        if delta_minutes > 0:
            izoh = f"Avtomatik: rejadagi {scheduled_minutes} daq o'rniga {att.worked_minutes} daq — {delta_minutes} daq ORTIQCHA"
        else:
            izoh = f"Avtomatik: rejadagi {scheduled_minutes} daq o'rniga {att.worked_minutes} daq — {-delta_minutes} daq KAM"
        # `auto_approve` — HR xohlasa nomzod darhol tasdiqlangan tug'iladi
        # (§3.2 to'siq C). Default O'CHIQ: tasdiqsiz pul payslip'ga kirmasin.
        entry = OvertimeEntry(
            user_id=user_id,
            date=for_date,
            minutes=delta_minutes,
            source="auto_attendance",
            status=(
                OvertimeEntryStatus.approved.value
                if getattr(profile, "auto_approve", False)
                else OvertimeEntryStatus.pending.value
            ),
            note=izoh,
        )
        db.add(entry)
        created.append(entry)
    return created


async def late_limit_event_for(db: AsyncSession, user: User, for_date: date) -> dict | None:
    """1.5-band (Shaffoflik): `for_date` (odatda "kecha") shu oyda xodimning
    bepul kechikish limitini birinchi marta OSHIRGAN yoki unga YAQINLASHTIRGAN
    kun bo'lsa — ogohlantirish turini qaytaradi, aks holda `None`.

    Holat HAR SAFAR `compute_late_fine`dan qaytadan hisoblanadi (alohida
    "allaqachon ogohlantirilgan" jadval/ustun YO'Q) — shu sabab faqat
    ANIQ `for_date`ga tegishli voqea tekshiriladi (masalan "shu kun birinchi
    jarimali kunmi"), umumiy "limit tugaganmi" holati EMAS — aks holda job
    har kuni qayta-qayta xabar yuborardi."""
    policy = await resolve_policy(db, user)
    if policy is None or policy.free_late_minutes_per_month is None:
        return None

    period = for_date.strftime("%Y-%m")
    days = await collect_attendance(db, user, period)
    late = compute_late_fine(days, policy)
    today_entry = next((d for d in late["detail"] if d["date"] == for_date.isoformat()), None)
    if today_entry is None:
        return None  # for_date kechikmagan yoki sababli edi

    free_limit = policy.free_late_minutes_per_month
    if today_entry["fined"]:
        earlier_fined = any(d["fined"] and d["date"] < today_entry["date"] for d in late["detail"])
        if earlier_fined:
            return None  # limit ilgariroq tugagan — bu yangi voqea emas
        return {"kind": "limit_reached", "fine_per_day": policy.fine_per_day}

    remaining_after = free_limit - (today_entry["cumulative_before"] + today_entry["late_minutes"])
    remaining_before = free_limit - today_entry["cumulative_before"]
    if remaining_after <= LATE_WARNING_BUFFER_MINUTES < remaining_before:
        return {"kind": "near_limit", "remaining_minutes": max(0, remaining_after)}
    return None
