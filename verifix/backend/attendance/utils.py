"""Geolokatsiya va vaqt hisoblash yordamchi funksiyalari."""
from __future__ import annotations
import math
from datetime import datetime, time, date as date_cls
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


def compute_late_minutes(check_in_dt: datetime, shift_start: time, grace_min: int = 0) -> int:
    """Smena boshlanish vaqtidan necha daqiqa kech qolganini hisoblaydi.

    Misol: shift 09:00, grace=5, keldi 09:15 -> 10 daq kechikish
           shift 09:00, grace=5, keldi 09:03 -> 0 daq (grace ichida)
           shift 09:00, grace=5, keldi 08:55 -> 0 daq (erta keldi)
    """
    if not check_in_dt or not shift_start:
        return 0
    local = _to_local(check_in_dt)
    scheduled = local.replace(
        hour=shift_start.hour, minute=shift_start.minute,
        second=0, microsecond=0,
    )
    diff_min = int((local - scheduled).total_seconds() // 60)
    if diff_min <= grace_min:
        return 0
    return diff_min - grace_min


def compute_early_minutes(check_out_dt: datetime, shift_end: time) -> int:
    """Smena tugashidan necha daqiqa erta ketganini hisoblaydi.

    Misol: shift end 18:00, ketdi 17:30 -> 30 daq erta
           shift end 18:00, ketdi 18:15 -> 0 daq (kech ketdi)
    """
    if not check_out_dt or not shift_end:
        return 0
    local = _to_local(check_out_dt)
    scheduled = local.replace(
        hour=shift_end.hour, minute=shift_end.minute,
        second=0, microsecond=0,
    )
    diff_min = int((scheduled - local).total_seconds() // 60)
    return max(0, diff_min)


def compute_worked_minutes(check_in_dt: datetime, check_out_dt: datetime) -> int:
    """Keldim va Ketdim orasidagi daqiqalar (umumiy ishlangan vaqt)."""
    if not check_in_dt or not check_out_dt:
        return 0
    diff = int((check_out_dt - check_in_dt).total_seconds() // 60)
    return max(0, diff)
