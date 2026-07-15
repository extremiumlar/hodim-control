"""Geolokatsiya va vaqt hisoblash yordamchi funksiyalari."""
from __future__ import annotations
import math
from datetime import datetime, time, timedelta, date as date_cls
from django.utils import timezone


def haversine_distance(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Ikki nuqta orasidagi masofa (metr)."""
    R = 6371000  # Yer radiusi (m)
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def is_weekend(d: date_cls, work_day_set: set[int]) -> bool:
    """ISO weekday: 1=Du..7=Ya. work_day_set ichida bo'lmasa - dam olish."""
    return d.isoweekday() not in work_day_set


def _to_local(dt: datetime) -> datetime:
    """Datetime'ni local timezone'ga keltirish (UTC dan localga)."""
    if timezone.is_naive(dt):
        return timezone.make_aware(dt, timezone.get_current_timezone())
    return timezone.localtime(dt)


def _is_night_shift(shift_start: time | None, shift_end: time | None) -> bool:
    """Smena yarim tundan oshadimi (masalan 22:00-06:00)?"""
    return bool(shift_start and shift_end and shift_end < shift_start)


def compute_late_minutes(
    check_in_dt: datetime, shift_start: time, grace_min: int = 0,
    shift_end: time | None = None,
) -> int:
    """Smena boshlanish vaqtidan necha daqiqa kech qolganini hisoblaydi.

    Misol: shift 09:00, grace=5, keldi 09:15 -> 10 daq kechikish
           shift 09:00, grace=5, keldi 09:03 -> 0 daq (grace ichida)
           shift 09:00, grace=5, keldi 08:55 -> 0 daq (erta keldi)

    Tungi smena (end < start, masalan 22:00-06:00): kelish yarim tundan keyin
    bo'lsa (mahalliy soat smena tugashidan oldin), boshlanish OLDINGI kunga
    tegishli — kechikish o'sha nuqtadan o'lchanadi.
    """
    if not check_in_dt or not shift_start:
        return 0
    local = _to_local(check_in_dt)
    scheduled = local.replace(
        hour=shift_start.hour, minute=shift_start.minute,
        second=0, microsecond=0,
    )
    if _is_night_shift(shift_start, shift_end) and local.time() < shift_end:
        scheduled -= timedelta(days=1)
    diff_min = int((local - scheduled).total_seconds() // 60)
    if diff_min <= grace_min:
        return 0
    return diff_min - grace_min


def compute_early_minutes(
    check_out_dt: datetime, shift_end: time,
    shift_start: time | None = None,
) -> int:
    """Smena tugashidan necha daqiqa erta ketganini hisoblaydi.

    Misol: shift end 18:00, ketdi 17:30 -> 30 daq erta
           shift end 18:00, ketdi 18:15 -> 0 daq (kech ketdi)

    Tungi smena (end < start): ketish yarim tundan OLDIN bo'lsa (mahalliy soat
    smena tugashidan katta), rejalashtirilgan tugash KEYINGI kunda — erta ketish
    shu nuqtaga nisbatan o'lchanadi.
    """
    if not check_out_dt or not shift_end:
        return 0
    local = _to_local(check_out_dt)
    scheduled = local.replace(
        hour=shift_end.hour, minute=shift_end.minute,
        second=0, microsecond=0,
    )
    if _is_night_shift(shift_start, shift_end) and local.time() > shift_end:
        scheduled += timedelta(days=1)
    diff_min = int((scheduled - local).total_seconds() // 60)
    return max(0, diff_min)


def compute_worked_minutes(check_in_dt: datetime, check_out_dt: datetime, shift=None) -> int:
    """Keldim va Ketdim orasidagi daqiqalar (umumiy ishlangan vaqt).

    Smenada tanaffus (break_start/break_end) belgilangan bo'lsa, [check_in,
    check_out] oralig'ining tanaffus bilan kesishgan qismi ayiriladi — tushlik
    ishlangan vaqtga kirmaydi. Shift yoki tanaffus yo'q bo'lsa xom span
    (avvalgi xatti-harakat) qaytadi.
    """
    if not check_in_dt or not check_out_dt:
        return 0
    diff = int((check_out_dt - check_in_dt).total_seconds() // 60)
    if diff <= 0:
        return 0
    if (shift is not None and shift.break_start and shift.break_end
            and shift.break_start < shift.break_end):
        in_local = _to_local(check_in_dt)
        out_local = _to_local(check_out_dt)
        b_start = in_local.replace(
            hour=shift.break_start.hour, minute=shift.break_start.minute,
            second=0, microsecond=0,
        )
        b_end = in_local.replace(
            hour=shift.break_end.hour, minute=shift.break_end.minute,
            second=0, microsecond=0,
        )
        overlap = int((min(out_local, b_end) - max(in_local, b_start)).total_seconds() // 60)
        diff -= max(0, overlap)
    return max(0, diff)
