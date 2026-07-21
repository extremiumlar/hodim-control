"""Kelib-ketish (davomat) logikasi — GPS + Face ID tekshiruvi va kechikish/ishlangan
vaqt hisobi. verifix (hodim_crm) `attendance/services.py` + `utils.py` dan yagona
FastAPI backendga birlashtirildi.

Farqlar (Django variantiga nisbatan):
- Kechikish alohida `Shift` modelidan emas, xodimning o'sha kungi amaldagi ish
  oynasidan (WorkScheduleOverride > WorkScheduleWeekly > default) hisoblanadi —
  soatlik reja bilan bir xil qoida (hourly_plan._effective_today).
- Vaqtlar bazaga naive-UTC (datetime.utcnow) yoziladi; kechikish mahalliy
  (Asia/Tashkent) devor-soati bo'yicha o'lchanadi.
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import settings
from api.routers.hourly_plan import _effective_today  # ish oynasi qoidasining yagona manbai
from api.timeutil import TASHKENT_TZ, today_local, work_minutes
from db.models import Attendance, AttendanceStatus, OfficeLocation, Role, User


# Davomat (kelib-ketish) kuzatiladigan rollar — BOSHLIQDAN TASHQARI HAMMA
# (xodim, HR, ROP, dasturchi). Boshliq jismoniy davomat ro'yxatlariga kirmaydi.
# Davomat bilan bog'liq HAMMA joyda (dashboard, statistika, digest, ish jadvali)
# shu yagona qoida ishlatiladi — aks holda web panel bilan guruh digesti turli
# sonlarni ko'rsatib qolardi.
ATTENDANCE_TRACKED_ROLES = tuple(r.value for r in Role if r is not Role.boss)


class CheckError(Exception):
    """Davomat xatosi — matni to'g'ridan-to'g'ri foydalanuvchiga ko'rsatiladi."""


def face_similarity(stored: list[float] | None, other: list[float] | None) -> float:
    """0..1 oraliqdagi o'xshashlik (1 = mukammal, 0 = boshqa odam). hodim_crm bilan
    bir xil: 1 - evklid masofa (face-api.js deskriptorlari ~0-1 masofada). Masofa
    > 1 bo'lsa 0 qaytadi."""
    if not stored or not other or len(stored) != len(other):
        return 0.0
    dist = math.sqrt(sum((a - b) ** 2 for a, b in zip(stored, other)))
    return max(0.0, 1.0 - dist)


def _validate_face(user: User, descriptor: list[float] | None, liveness: float) -> float:
    """Yuz tekshiruvi: ro'yxatdan o'tgan + tiriklik + o'xshashlik. O'xshashlikni
    qaytaradi; xato bo'lsa CheckError."""
    if not user.has_face:
        raise CheckError("Sizning yuzingiz hali ro'yxatdan o'tmagan. Avval «Yuzni ro'yxatdan o'tkazish».")
    if not descriptor or len(descriptor) != 128:
        raise CheckError("Yuz ma'lumoti yuborilmagan yoki noto'g'ri formatda.")
    if liveness < settings.face_liveness_threshold:
        raise CheckError(
            f"Tiriklik tekshiruvi muvaffaqiyatsiz ({liveness:.2f} < {settings.face_liveness_threshold})."
        )
    try:
        stored = json.loads(user.face_descriptor) if user.face_descriptor else None
    except (ValueError, TypeError):
        stored = None
    sim = face_similarity(stored, descriptor)
    if sim < settings.face_similarity_threshold:
        raise CheckError(
            f"Yuz mos kelmadi (o'xshashlik {sim:.2f} < {settings.face_similarity_threshold}). "
            "Siz ro'yxatdan o'tgan foydalanuvchimisiz?"
        )
    return sim


def haversine_distance(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Ikki nuqta orasidagi masofa (metr)."""
    r = 6371000  # Yer radiusi (m)
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _minute_of_day(dt: datetime) -> int:
    return dt.hour * 60 + dt.minute


def _hm_to_min(hm: str) -> int:
    h, m = hm.split(":")
    return int(h) * 60 + int(m)


async def _nearest_active_office(
    db: AsyncSession, lat: float, lng: float
) -> tuple[OfficeLocation | None, int | None]:
    """Berilgan nuqtaga eng yaqin FAOL ofis va ungacha masofa (metr)."""
    offices = list(await db.scalars(select(OfficeLocation).where(OfficeLocation.is_active.is_(True))))
    best: OfficeLocation | None = None
    best_d: float | None = None
    for o in offices:
        d = haversine_distance(float(o.latitude), float(o.longitude), lat, lng)
        if best_d is None or d < best_d:
            best_d, best = d, o
    return best, (int(best_d) if best_d is not None else None)


async def _validate_location(db: AsyncSession, lat: float, lng: float) -> int:
    office, dist = await _nearest_active_office(db, lat, lng)
    if office is None or dist is None:
        raise CheckError("Tizimda faol ofis manzili sozlanmagan. Rahbaringizga murojaat qiling.")
    if dist > office.radius_meters:
        raise CheckError(
            f"Siz ofis hududidan tashqaridasiz (~{dist} m, «{office.name}»). Avval ofisga keling."
        )
    return dist


def _apply_status(att: Attendance, is_working: bool) -> None:
    """check_in/check_out va is_working asosida is_weekend + status ni belgilaydi."""
    att.is_weekend = not is_working
    if not is_working:
        att.status = AttendanceStatus.weekend.value
    elif att.check_in_time is None:
        att.status = AttendanceStatus.absent.value
    elif att.late_minutes > 0:
        att.status = AttendanceStatus.late.value
    else:
        att.status = AttendanceStatus.present.value


async def perform_check_in(
    db: AsyncSession,
    user: User,
    lat: float,
    lng: float,
    descriptor: list[float] | None = None,
    liveness: float = 0.0,
) -> Attendance:
    """Xodimni bugungi kunga «Keldim» qiladi. Yuz (Face ID) tasdiqlangan va GPS ofis
    radiusida bo'lishi shart. Kechikish o'sha kungi ish oynasi boshlanishidan
    (grace bilan) hisoblanadi."""
    day = today_local()
    is_working, start, _end = await _effective_today(db, user, day)

    _validate_face(user, descriptor, liveness)
    dist = await _validate_location(db, lat, lng)

    att = await db.scalar(
        select(Attendance).where(Attendance.user_id == user.id, Attendance.date == day)
    )
    if att is not None and att.check_in_time is not None:
        raise CheckError("Siz bugun allaqachon «Keldim» qilgansiz.")
    if att is None:
        att = Attendance(user_id=user.id, date=day)
        db.add(att)

    now_local = datetime.now(TASHKENT_TZ)
    att.check_in_time = datetime.utcnow()
    att.check_in_lat = lat
    att.check_in_lng = lng
    att.check_in_distance_m = dist

    if is_working and start:
        diff = _minute_of_day(now_local) - _hm_to_min(start)
        grace = settings.attendance_grace_minutes
        att.late_minutes = max(0, diff - grace) if diff > grace else 0
    else:
        att.late_minutes = 0

    _apply_status(att, is_working)
    await db.commit()
    await db.refresh(att)
    return att


async def perform_check_out(
    db: AsyncSession,
    user: User,
    lat: float,
    lng: float,
    descriptor: list[float] | None = None,
    liveness: float = 0.0,
) -> Attendance:
    """Xodimni «Ketdim» qiladi. GPS + yuz tasdiqlanadi. Erta ketish ish oynasi
    tugashidan, ishlangan vaqt check-in/out orasidan hisoblanadi."""
    day = today_local()
    is_working, start, end = await _effective_today(db, user, day)

    att = await db.scalar(
        select(Attendance).where(Attendance.user_id == user.id, Attendance.date == day)
    )
    if att is None or att.check_in_time is None:
        raise CheckError("Avval «Keldim» qilishingiz kerak.")
    if att.check_out_time is not None:
        raise CheckError("Siz bugun allaqachon «Ketdim» qilgansiz.")

    _validate_face(user, descriptor, liveness)
    await _validate_location(db, lat, lng)

    now_local = datetime.now(TASHKENT_TZ)
    att.check_out_time = datetime.utcnow()
    att.check_out_lat = lat
    att.check_out_lng = lng

    if is_working and end:
        diff = _hm_to_min(end) - _minute_of_day(now_local)
        att.early_leave_minutes = max(0, diff)
    else:
        att.early_leave_minutes = 0

    # Ishlangan vaqt — soatlik reja bilan BIR XIL ta'rif (timeutil.work_minutes):
    # tushlik (13:00–14:00) chiqariladi, ish kunida faqat ish oynasi [start, end]
    # bilan kesishgan qism sanaladi (erta kelib o'tirish yoki kech qolib ketish
    # ishlangan soatni shishirmaydi). Dam olish kunida oyna yo'q — kelish-ketish
    # oralig'ining o'zi (tushliksiz) olinadi. work_minutes teskari oraliqda 0
    # qaytaradi, shuning uchun manfiy chiqmaydi.
    check_in_local = att.check_in_time.replace(tzinfo=timezone.utc).astimezone(TASHKENT_TZ)
    in_min = _minute_of_day(check_in_local)
    out_min = _minute_of_day(now_local)
    if is_working and start and end:
        worked = work_minutes(max(in_min, _hm_to_min(start)), min(out_min, _hm_to_min(end)))
    else:
        worked = work_minutes(in_min, out_min)
    att.worked_minutes = max(0, worked)

    _apply_status(att, is_working)
    await db.commit()
    await db.refresh(att)
    return att
