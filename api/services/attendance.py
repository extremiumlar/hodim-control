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
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
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


async def _validate_location(
    db: AsyncSession, lat: float, lng: float, accuracy: float | None = None
) -> int:
    # GPS aniqligi — brauzer o'zi hisoblab yuboradi. Juda yomon o'qish (masalan
    # tarmoq/IP-asosidagi zaxira geolokatsiya, ba'zan 1000+ metr xato) ofis
    # radiusini ma'nosiz qiladi: xato tasodifan radius ichiga tushib qolishi mumkin.
    if accuracy is not None and accuracy > settings.attendance_max_gps_accuracy_m:
        raise CheckError(
            f"GPS aniqligi yetarli emas (~{accuracy:.0f} m). Ochiq joyga chiqib qayta urinib ko'ring."
        )
    office, dist = await _nearest_active_office(db, lat, lng)
    if office is None or dist is None:
        raise CheckError("Tizimda faol ofis manzili sozlanmagan. Rahbaringizga murojaat qiling.")
    if dist > office.radius_meters:
        raise CheckError(
            f"Siz ofis hududidan tashqaridasiz (~{dist} m, «{office.name}»). Avval ofisga keling."
        )
    return dist


async def find_similar_face(
    db: AsyncSession, descriptor: list[float], exclude_user_id: int | None = None
) -> tuple[User, float] | None:
    """Berilgan descriptor bazadagi BOSHQA (`exclude_user_id`dan tashqari) ro'yxatdan
    o'tgan yuzlarning birortasiga chegaradan yaqinmi — tekshiradi. Ro'yxatdan
    o'tishda (birinchi marta yoki qayta) chaqiriladi: bir kishi ikkinchisining
    yuzi bilan (yoki tasodifan bir xil ro'yxatdan o'tish orqali) ro'yxatdan
    o'tib olishining oldini oladi. Eng o'xshash (eng yuqori similarity) juftlikni
    qaytaradi, hech kim chegaradan o'tmasa `None`."""
    query = select(User).where(User.face_descriptor.isnot(None))
    if exclude_user_id is not None:
        query = query.where(User.id != exclude_user_id)
    best_user: User | None = None
    best_sim = -1.0
    for other in await db.scalars(query):
        try:
            other_desc = json.loads(other.face_descriptor) if other.face_descriptor else None
        except (ValueError, TypeError):
            continue
        sim = face_similarity(other_desc, descriptor)
        if sim > best_sim:
            best_sim, best_user = sim, other
    if best_user is not None and best_sim >= settings.face_similarity_threshold:
        return best_user, best_sim
    return None


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
    accuracy: float | None = None,
) -> Attendance:
    """Xodimni bugungi kunga «Keldim» qiladi. Yuz (Face ID) tasdiqlangan va GPS ofis
    radiusida bo'lishi shart. Kechikish o'sha kungi ish oynasi boshlanishidan
    (grace bilan) hisoblanadi."""
    day = today_local()
    is_working, start, end = await _effective_today(db, user, day)

    _validate_face(user, descriptor, liveness)
    dist = await _validate_location(db, lat, lng, accuracy)

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
        # Grace — BO'SAG'A, chegirma emas: grace ichida kelinsa kechikish 0,
        # undan oshsa TO'LIQ farq yoziladi (masalan grace=5, kelish 09:06 bo'lsa
        # late=6, "6-5=1" EMAS). Ilgari har kechikkan kun grace daqiqasiga kam
        # ko'rsatilardi — oylik statistikada sezilarli xato edi. Mavjud yozuvlar
        # bu tuzatishdan keyin ham eski (kamaytirilgan) qiymatda qoladi — bu
        # yerdagi o'zgarish faqat YANGI check-in'larga qo'llanadi.
        late = diff if diff > grace else 0
        # Yuqori chegara: ish oynasi uzunligidan (tushliksiz) oshib ketmasin —
        # aks holda 17:59 da (deyarli kun oxirida) kelgan xodim "534 daqiqa
        # kechikdi" bo'lib yozilib, oylik jamni bitta kun portlatib yuboradi.
        # Bunday holat mohiyatan "kunning katta qismini yo'q qilish" — kechikish
        # sifatida emas, mantiqiy jihatdan ish oynasi bilan chegaralanadi.
        if end:
            window = work_minutes(_hm_to_min(start), _hm_to_min(end))
            late = min(late, window)
        att.late_minutes = late
    else:
        att.late_minutes = 0

    _apply_status(att, is_working)
    try:
        await db.commit()
    except IntegrityError:
        # 2.3-band: ikkita bir vaqtli check-in so'rovi ikkalasi ham `att is None`
        # ko'rishi mumkin (SELECT-then-INSERT, qulfsiz) — ikkalasi ham INSERT qiladi,
        # `uq_attendance_user_date` ikkinchisini rad etadi. Jonli isbot: parallel
        # so'rov [200, 500] qaytargan. Endi tushunarli 400 xabar beriladi, 500 EMAS.
        await db.rollback()
        raise CheckError("Siz bugun allaqachon «Keldim» qilgansiz.")
    await db.refresh(att)
    return att


# 2.1-band: yarim tundan keyin "Ketdim" bosilsa, kechagi ochiq yozuvni izlashda
# qo'llaniladigan oyna — bundan uzoqroq (masalan bir necha kun oldingi) ochiq
# yozuvlar avtomatik yopilmaydi, faqat "hozirgina yarim tundan o'tib qolgan"
# holat qamrab olinadi.
POST_MIDNIGHT_WINDOW_HOURS = 6


async def perform_check_out(
    db: AsyncSession,
    user: User,
    lat: float,
    lng: float,
    descriptor: list[float] | None = None,
    liveness: float = 0.0,
    accuracy: float | None = None,
) -> Attendance:
    """Xodimni «Ketdim» qiladi. GPS + yuz tasdiqlanadi. Erta ketish ish oynasi
    tugashidan, ishlangan vaqt check-in/out orasidan hisoblanadi."""
    today = today_local()
    now_local = datetime.now(TASHKENT_TZ)

    att = await db.scalar(
        select(Attendance).where(Attendance.user_id == user.id, Attendance.date == today)
    )
    crossed_midnight = False
    if att is None or att.check_in_time is None:
        # 2.1-band: bugun ochiq yozuv yo'q — kechagi kundan qolgan ochiq yozuvni
        # tekshiramiz (masalan 23:00 check-in, 00:30 check-out — kalendar kun
        # almashgan, lekin bu HALI O'SHA ish smenasi). Jonli isbot: bunday holatda
        # yozuv abadiy check_out_time=NULL bo'lib qolar edi.
        yesterday = today - timedelta(days=1)
        prev = await db.scalar(
            select(Attendance).where(
                Attendance.user_id == user.id,
                Attendance.date == yesterday,
                Attendance.check_in_time.isnot(None),
                Attendance.check_out_time.is_(None),
            )
        )
        if prev is not None:
            checkin_local = prev.check_in_time.replace(tzinfo=timezone.utc).astimezone(TASHKENT_TZ)
            hours_since = (now_local - checkin_local).total_seconds() / 3600
            if 0 <= hours_since <= POST_MIDNIGHT_WINDOW_HOURS:
                att = prev
                crossed_midnight = True
        if att is None or att.check_in_time is None:
            raise CheckError("Avval «Keldim» qilishingiz kerak.")
    if att.check_out_time is not None:
        raise CheckError("Siz bugun allaqachon «Ketdim» qilgansiz.")

    # Yozuvning O'Z sanasi bo'yicha ish oynasi — kechagi yozuv bo'lsa ham kechagi
    # jadval ishlatiladi, bugungisi EMAS (masalan dam olish kunidan keyin ishga
    # chiqqan kun bilan aralashmasin).
    is_working, start, end = await _effective_today(db, user, att.date)

    _validate_face(user, descriptor, liveness)
    await _validate_location(db, lat, lng, accuracy)

    check_out_time_utc = datetime.utcnow()

    if crossed_midnight:
        # Kun chegarasidan oshib ketgan — devor-soati (minute-of-day) arifmetikasi
        # endi ma'nosiz (chiqish vaqti kirish vaqtidan "kichik" ko'rinadi). Shu
        # sababli haqiqiy o'tgan vaqt (real datetime farqi) olinadi, ish
        # oynasi/tushlik chegirmasi qo'llanilmaydi — bu holat allaqachon oddiy
        # ish kuni chegarasidan tashqari.
        early_leave_minutes = 0
        elapsed = (check_out_time_utc - att.check_in_time).total_seconds() / 60
        worked_minutes = max(0, round(elapsed))
    else:
        if is_working and end:
            diff = _hm_to_min(end) - _minute_of_day(now_local)
            early = max(0, diff)
            # Yuqori chegara — 1.4-band bilan bir xil sabab: check-in darhol keyin
            # check-out qilinsa (masalan sinov yoki xato bosish), "erta ketish" ish
            # oynasidan oshib ketmasin.
            if start:
                window = work_minutes(_hm_to_min(start), _hm_to_min(end))
                early = min(early, window)
            early_leave_minutes = early
        else:
            early_leave_minutes = 0

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
        worked_minutes = max(0, worked)

    status = AttendanceStatus.weekend.value if not is_working else (
        AttendanceStatus.late.value if att.late_minutes > 0 else AttendanceStatus.present.value
    )

    # 2.3-band bilan bir xil sabab: ikkita bir vaqtli check-out so'rovi ikkalasi
    # ham `check_out_time is None` ko'rishi mumkin (yuqoridagi SELECT, qulfsiz).
    # ORM mutate-then-commit o'rniga ATOMIK UPDATE ... WHERE check_out_time IS NULL
    # ishlatiladi — faqat BITTASI muvaffaqiyatli bo'ladi, ikkinchisi aniq xabar oladi
    # (avvalgisining ma'lumotini "so'nggi yozuvchi g'olib" tarzida ustidan yozmaydi).
    result = await db.execute(
        update(Attendance)
        .where(Attendance.id == att.id, Attendance.check_out_time.is_(None))
        .values(
            check_out_time=check_out_time_utc,
            check_out_lat=lat,
            check_out_lng=lng,
            early_leave_minutes=early_leave_minutes,
            worked_minutes=worked_minutes,
            is_weekend=not is_working,
            status=status,
        )
    )
    if result.rowcount == 0:
        await db.rollback()
        raise CheckError("Siz bugun allaqachon «Ketdim» qilgansiz.")
    await db.commit()
    await db.refresh(att)
    return att
