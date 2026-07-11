"""Check-in / Check-out logikasi (GPS + Face ID tekshiruvi).

Tekshiruvlar:
1. GPS — hodim ofis radiusi ichidami?
2. Tiriklik (liveness) — ≥ settings.FACE_LIVENESS_THRESHOLD
3. Yuz o'xshashligi (similarity) — ≥ settings.FACE_SIMILARITY_THRESHOLD

Hisoblash (kechikish, ishlangan vaqt) `Attendance.save()` ichida avtomatik.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from django.conf import settings
from django.utils import timezone

from .models import Attendance
from .utils import haversine_distance


class CheckInError(Exception):
    """Check-in xatosi (foydalanuvchiga ko'rsatiladi)."""


@dataclass
class CheckInPayload:
    latitude: float
    longitude: float
    face_descriptor: list[float] | None = None
    liveness: float = 0.0


def _validate_office(user, payload: CheckInPayload) -> int:
    office = user.office
    if office is None or not office.is_active:
        raise CheckInError("Sizga ofis biriktirilmagan. Adminga murojaat qiling.")

    distance = haversine_distance(
        float(office.latitude), float(office.longitude),
        payload.latitude, payload.longitude,
    )
    if distance > office.radius_meters:
        raise CheckInError(
            f"Siz ofis hududidan tashqaridasiz ({int(distance)} m). "
            f"Avval ofisga keling."
        )
    return int(distance)


def _validate_face(user, payload: CheckInPayload) -> float:
    """Yuz tekshiruvi: tiriklik + o'xshashlik."""
    if not user.has_face:
        raise CheckInError(
            "Sizning yuzingiz hali ro'yxatdan o'tmagan. "
            "Avval profilingizda yuz rasmingizni yuklang."
        )
    if not payload.face_descriptor or len(payload.face_descriptor) != 128:
        raise CheckInError("Yuz ma'lumoti yuborilmagan yoki noto'g'ri formatda.")

    # Tiriklik tekshiruvi
    if payload.liveness < settings.FACE_LIVENESS_THRESHOLD:
        raise CheckInError(
            f"Tiriklik tekshiruvi muvaffaqiyatsiz "
            f"({payload.liveness:.2f} < {settings.FACE_LIVENESS_THRESHOLD})."
        )

    sim = user.face_similarity(payload.face_descriptor)
    if sim < settings.FACE_SIMILARITY_THRESHOLD:
        raise CheckInError(
            f"Yuz mos kelmadi (o'xshashlik {sim:.2f} < {settings.FACE_SIMILARITY_THRESHOLD}). "
            f"Siz ro'yxatdan o'tgan foydalanuvchimi?"
        )
    return sim


def perform_check_in(user, payload: CheckInPayload) -> Attendance:
    if user.is_on_leave:
        raise CheckInError("Siz ta'tildasiz. Adminga murojaat qiling.")
    if user.shift is None:
        raise CheckInError("Sizga smena biriktirilmagan.")

    distance = _validate_office(user, payload)
    _validate_face(user, payload)

    today = timezone.localdate()
    now = timezone.localtime()

    att, _ = Attendance.objects.get_or_create(user=user, date=today)
    if att.check_in_time:
        raise CheckInError("Siz bugun allaqachon check-in qilgansiz.")

    att.check_in_time = now
    att.check_in_lat = Decimal(str(payload.latitude))
    att.check_in_lng = Decimal(str(payload.longitude))
    att.check_in_distance_m = distance
    att.save()
    return att


def perform_check_out(user, payload: CheckInPayload) -> Attendance:
    today = timezone.localdate()
    try:
        att = Attendance.objects.get(user=user, date=today)
    except Attendance.DoesNotExist:
        raise CheckInError("Avval check-in qilishingiz kerak.")
    if not att.check_in_time:
        raise CheckInError("Avval check-in qilishingiz kerak.")
    if att.check_out_time:
        raise CheckInError("Siz bugun allaqachon check-out qilgansiz.")

    _validate_office(user, payload)
    _validate_face(user, payload)

    now = timezone.localtime()
    att.check_out_time = now
    att.check_out_lat = Decimal(str(payload.latitude))
    att.check_out_lng = Decimal(str(payload.longitude))
    att.save()
    return att
