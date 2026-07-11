"""Avtomatik oylik hisoblash.

Formula:
    Kunlik stavka      = asosiy_oylik / oydagi_ish_kunlari
    Kelmagan ayirma    = kunlik_stavka * kelmagan_kunlar
    Dam olish qo'shimcha = kunlik_stavka * (weekend_rate%) * dam_olishda_ishlagan
    Kechikish jarima    = 1_daq_jarima * jami_kechikish_daqiqa

    YAKUNIY = asosiy_oylik
              - kelmagan_ayirma
              - kechikish_jarima
              - boshqa_jarima
              + dam_olish_qo'shimcha
              + bonus
"""
from __future__ import annotations
from calendar import monthrange
from datetime import date
from decimal import Decimal

from django.db.models import Sum

from accounts.models import User
from attendance.models import Attendance
from .models import MonthlyPayroll, Bonus, Penalty

CENT = Decimal("0.01")


def _parse_period(period: str) -> tuple[int, int]:
    y, m = period.split("-")
    return int(y), int(m)


def compute_payroll(user: User, period: str) -> MonthlyPayroll:
    """Berilgan oy uchun hodim oyligini hisoblaydi va saqlaydi."""
    year, month = _parse_period(period)
    days_in_month = monthrange(year, month)[1]
    start = date(year, month, 1)
    end = date(year, month, days_in_month)

    # Hodimning shaxsiy ish kunlari (5 yoki 6 kunlik)
    work_day_set = user.work_day_set()
    work_days_total = sum(
        1 for d in range(1, days_in_month + 1)
        if date(year, month, d).isoweekday() in work_day_set
    )

    atts = Attendance.objects.filter(user=user, date__gte=start, date__lte=end)
    worked = atts.filter(check_in_time__isnull=False).count()
    late_min = atts.aggregate(s=Sum("late_minutes"))["s"] or 0
    weekend_worked = atts.filter(is_weekend=True, check_in_time__isnull=False).count()

    # Kelmagan ish kunlari = jami ish kunlari - ish kunida kelganlar
    present_workdays = atts.filter(
        is_weekend=False, check_in_time__isnull=False
    ).count()
    absent = max(0, work_days_total - present_workdays)

    base = Decimal(user.base_salary or 0)
    # Aniq kunlik stavka (yaxlitlamasdan) - hisob uchun
    per_day_exact = (base / work_days_total) if work_days_total else Decimal("0")
    per_day = per_day_exact.quantize(CENT)  # ko'rsatish uchun

    # 1 kun kelmasa -> kunlik stavka ayiriladi (base'dan oshib ketmasin)
    absence_deduction = min((per_day_exact * absent).quantize(CENT), base)

    # Dam olish kuni qo'shimchasi
    weekend_rate = Decimal(user.weekend_rate or 0) / Decimal("100")
    weekend_extra = (per_day_exact * weekend_rate * weekend_worked).quantize(CENT)

    # Kechikish jarimasi
    late_penalty = (Decimal(user.late_penalty_per_minute or 0) * late_min).quantize(CENT)

    bonus_total = Bonus.objects.filter(user=user, period=period).aggregate(
        s=Sum("amount"))["s"] or Decimal("0")
    penalty_total = Penalty.objects.filter(user=user, period=period).aggregate(
        s=Sum("amount"))["s"] or Decimal("0")

    total = (
        base
        - absence_deduction
        - late_penalty
        - penalty_total
        + weekend_extra
        + bonus_total
    ).quantize(CENT)

    payroll, _ = MonthlyPayroll.objects.update_or_create(
        user=user, period=period,
        defaults=dict(
            base_salary=base.quantize(CENT),
            per_day_rate=per_day,
            absence_deduction=absence_deduction,
            weekend_extra=weekend_extra,
            bonus_total=bonus_total,
            penalty_total=penalty_total,
            late_penalty_total=late_penalty,
            total=total,
            work_days_total=work_days_total,
            worked_days=worked,
            weekend_days=weekend_worked,
            late_minutes=late_min,
            absent_days=absent,
        ),
    )
    return payroll


def compute_payroll_for_all(period: str) -> list[MonthlyPayroll]:
    return [compute_payroll(u, period) for u in User.objects.filter(is_active=True)]
