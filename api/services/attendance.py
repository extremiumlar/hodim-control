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
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import settings
from api.routers.hourly_plan import _effective_today  # ish oynasi qoidasining yagona manbai
from api.timeutil import TASHKENT_TZ, today_local, work_minutes
from db.models import Attendance, AttendanceStatus, ExcusedDay, ExcusedStatus, OfficeLocation, Role, User


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


async def _validate_location(
    db: AsyncSession, lat: float | None, lng: float | None, accuracy: float | None = None,
    user: User | None = None,
) -> int | None:
    # «Bez lokatsiya» ruxsati (`User.skip_location_check`): doimiy ob'ektda
    # yurmaydigan xodim (mobilograf, kuryer, ko'chma sotuv) istalgan joydan
    # bosa oladi. GPS aniqligi ham tekshirilmaydi — chunki masofa baribir
    # ishlatilmaydi. `None` qaytadi: "masofa o'lchanmadi" (0 EMAS — 0 "ofis
    # markazida turibdi" degan soxta ma'no berardi).
    # Face ID bu yerda BEKOR QILINMAYDI — u `_validate_face`da alohida.
    if user is not None and user.skip_location_check:
        return None

    # Ruxsati YO'Q xodim koordinatasiz kelsa — bu eski frontend yoki qo'lda
    # yasalgan so'rov. Jimgina o'tkazib yuborilsa, GPS tekshiruvini istalgan
    # kishi `latitude: null` yuborib chetlab o'tardi.
    if lat is None or lng is None:
        raise CheckError("Joylashuv aniqlanmadi. GPS'ni yoqib qayta urinib ko'ring.")

    # GPS aniqligi — brauzer o'zi hisoblab yuboradi. Juda yomon o'qish (masalan
    # tarmoq/IP-asosidagi zaxira geolokatsiya, ba'zan 1000+ metr xato) ofis
    # radiusini ma'nosiz qiladi: xato tasodifan radius ichiga tushib qolishi mumkin.
    if accuracy is not None and accuracy > settings.attendance_max_gps_accuracy_m:
        raise CheckError(
            f"GPS aniqligi yetarli emas (~{accuracy:.0f} m). Ochiq joyga chiqib qayta urinib ko'ring."
        )
    offices = list(await db.scalars(select(OfficeLocation).where(OfficeLocation.is_active.is_(True))))
    if not offices:
        raise CheckError("Tizimda faol ofis manzili sozlanmagan. Rahbaringizga murojaat qiling.")

    # 3.2-band: "ENG YAQIN ofis"ning radiusi emas — BIRORTA faol ofis radiusi
    # ichidami tekshiriladi. Ilgari: A ofis 100m (radius 50) yaqinroq bo'lgani
    # uchun tanlanardi, B ofis 120m (radius 200) — xodim aslida B radiusida
    # bo'lsa ham, "eng yaqin" A ekani sabab RAD ETILARDI.
    best_dist: float | None = None
    for o in offices:
        d = haversine_distance(float(o.latitude), float(o.longitude), lat, lng)
        if best_dist is None or d < best_dist:
            best_dist = d
        if d <= o.radius_meters:
            return int(d)

    raise CheckError(
        f"Siz ofis hududidan tashqaridasiz (~{int(best_dist)} m). Avval ofisga keling."
    )


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


async def is_excused_day(db: AsyncSession, user_id: int, day: date) -> bool:
    """5.1-band: shu kunga TASDIQLANGAN sababli kun so'rovi bormi. Faqat
    `approved` — `pending` yoki `rejected` davomatga ta'sir qilmasligi kerak."""
    row = await db.scalar(
        select(ExcusedDay).where(
            ExcusedDay.user_id == user_id,
            ExcusedDay.date == day,
            ExcusedDay.status == ExcusedStatus.approved.value,
        )
    )
    return row is not None


def _apply_status(att: Attendance, is_working: bool, is_excused: bool = False) -> None:
    """check_in/check_out va is_working asosida is_weekend + status ni belgilaydi."""
    att.is_weekend = not is_working
    if not is_working:
        att.status = AttendanceStatus.weekend.value
    elif is_excused:
        # Tasdiqlangan sababli kun — kelgan bo'lsa ham "kech qolgan" emas,
        # alohida holat (late_minutes chaqiruvchi tomonidan 0 qilinadi).
        att.status = AttendanceStatus.excused.value
    elif att.check_in_time is None:
        att.status = AttendanceStatus.absent.value
    elif att.late_minutes > 0:
        att.status = AttendanceStatus.late.value
    else:
        att.status = AttendanceStatus.present.value


def _to_local(dt_utc: datetime | None) -> datetime | None:
    """Bazadagi naive-UTC vaqtni mahalliy (Asia/Tashkent) devor-soatiga o'giradi."""
    if dt_utc is None:
        return None
    return dt_utc.replace(tzinfo=timezone.utc).astimezone(TASHKENT_TZ)


def local_hm_to_utc(day: date, hm: str) -> datetime:
    """Mahalliy "HH:MM" (berilgan sanada) → bazaga yoziladigan naive-UTC.
    HR qo'lda tuzatishida ishlatiladi: rahbar devor-soatini kiritadi, baza esa
    hamma joyda naive-UTC saqlaydi."""
    h, m = (int(part) for part in hm.split(":"))
    local = datetime(day.year, day.month, day.day, h, m, tzinfo=TASHKENT_TZ)
    return local.astimezone(timezone.utc).replace(tzinfo=None)


def recompute_fields(att: Attendance, is_working: bool, start: str, end: str, is_excused: bool = False) -> None:
    """Yozuvdagi kelish/ketish vaqtlaridan `late_minutes`, `early_leave_minutes`,
    `worked_minutes` va `status` ni QAYTA hisoblaydi. HR qo'lda tuzatishi
    (`PUT /attendance/manual`) shu funksiyadan foydalanadi.

    Vaqtlar `att` ning O'ZIDAN o'qiladi (`datetime.now()` dan emas) — shu sababli
    o'tgan kunni ham qayta hisoblash mumkin; `perform_check_in/out` esa "hozir"
    bo'yicha ishlaydi va o'z qo'shimcha shartlari bor (yarim tundan oshgan smena,
    atomik UPDATE bilan poyga himoyasi), shuning uchun ular alohida qolgan.
    Qoidalar — grace bo'sag'asi, ish oynasi bilan chegaralash, tushlik chegirmasi —
    ular bilan AYNAN bir xil bo'lishi shart; birini o'zgartirsangiz, ikkinchisini
    ham o'zgartiring.

    `is_excused` — 5.1-band: tasdiqlangan sababli kun bo'lsa kechikish/erta
    ketish 0 qilinadi (xodim shifokordan keyin kech kelgan bo'lishi mumkin,
    bu "kechikish" emas)."""
    in_local = _to_local(att.check_in_time)
    out_local = _to_local(att.check_out_time)
    window = work_minutes(_hm_to_min(start), _hm_to_min(end)) if (start and end) else None

    # Kechikish. Grace — BO'SAG'A, chegirma emas: grace ichida kelinsa kechikish 0,
    # undan oshsa TO'LIQ farq yoziladi (masalan grace=5, kelish 09:06 bo'lsa
    # late=6, "6-5=1" EMAS). Ilgari har kechikkan kun grace daqiqasiga kam
    # ko'rsatilardi — oylik statistikada sezilarli xato edi.
    if is_working and start and in_local is not None and not is_excused:
        diff = _minute_of_day(in_local) - _hm_to_min(start)
        late = diff if diff > settings.attendance_grace_minutes else 0
        # Yuqori chegara: ish oynasi uzunligidan (tushliksiz) oshib ketmasin —
        # aks holda 17:59 da (deyarli kun oxirida) kelgan xodim "534 daqiqa
        # kechikdi" bo'lib yozilib, oylik jamni bitta kun portlatib yuboradi.
        if window is not None:
            late = min(late, window)
        att.late_minutes = late
    else:
        att.late_minutes = 0

    # Erta ketish — yuqori chegara bir xil sabab bilan (check-in'dan darhol keyin
    # check-out qilinsa, "erta ketish" ish oynasidan oshmasin).
    if is_working and end and out_local is not None and not is_excused:
        early = max(0, _hm_to_min(end) - _minute_of_day(out_local))
        if window is not None:
            early = min(early, window)
        att.early_leave_minutes = early
    else:
        att.early_leave_minutes = 0

    # Ishlangan vaqt — soatlik reja bilan BIR XIL ta'rif (timeutil.work_minutes):
    # tushlik (13:00–14:00) chiqariladi, ish kunida faqat ish oynasi [start, end]
    # bilan kesishgan qism sanaladi (erta kelib o'tirish yoki kech qolib ketish
    # ishlangan soatni shishirmaydi). Dam olish kunida oyna yo'q — kelish-ketish
    # oralig'ining o'zi (tushliksiz) olinadi.
    if in_local is not None and out_local is not None:
        in_min, out_min = _minute_of_day(in_local), _minute_of_day(out_local)
        if is_working and start and end:
            worked = work_minutes(max(in_min, _hm_to_min(start)), min(out_min, _hm_to_min(end)))
        else:
            worked = work_minutes(in_min, out_min)
        att.worked_minutes = max(0, worked)
    else:
        att.worked_minutes = 0

    _apply_status(att, is_working, is_excused)


async def recompute_attendance(db: AsyncSession, att: Attendance, user: User) -> None:
    """`recompute_fields` ning DB varianti — o'sha kungi amaldagi ish oynasini
    (override > haftalik > default) o'zi topadi."""
    is_working, start, end = await _effective_today(db, user, att.date)
    is_excused = await is_excused_day(db, user.id, att.date)
    recompute_fields(att, is_working, start, end, is_excused)


AUTO_CLOSED_MARK = "Avtomatik yopildi"


async def collect_readiness(db: AsyncSession, date_from: date, date_to: date) -> dict:
    """Davomat ma'lumotining berilgan davr bo'yicha TAYYORLIK hisoboti.

    Nima uchun kerak: davomat raqamlari pulga aylanganda (kechikish jarimasi,
    soatbay to'lov) har bir "bo'sh joy" real nizoga aylanadi. Oylik hisobdan
    oldin rahbar shu ro'yxatni ko'rib, avval tuzatishi kerak:

    - `no_schedule`   — ish jadvali umuman belgilanmagan xodim: unga default
                        (Du–Ju 09:00–18:00) qo'llanadi, ya'ni kechikishi
                        TAXMIN asosida hisoblanadi.
    - `open_checkouts`— «Keldim» bor, «Ketdim» yo'q (bugundan oldingi kunlar).
                        Kechki avtomatik yopish ishlamay qolgan holat.
    - `auto_closed`   — avtomatik yopilgan kunlar: ishlangan vaqt haqiqiy emas,
                        taxminiy (ish oynasi oxiri bo'yicha).
    - `pending_excused` — hal qilinmagan sababli kun so'rovi: tasdiqlansa
                        jarima bekor bo'ladi, shuning uchun avval hal qilinsin.
    - `no_face`       — yuzi ro'yxatdan o'tmagan xodim: umuman check-in
                        qila olmaydi, ya'ni "kelmagan" bo'lib chiqaveradi.
    """
    from db.models import ExcusedDay, ExcusedStatus, WorkScheduleOverride, WorkScheduleWeekly

    users = list(
        await db.scalars(
            select(User).where(
                User.role.in_(ATTENDANCE_TRACKED_ROLES), User.is_active.is_(True)
            )
        )
    )
    names = {u.id: u.full_name for u in users}
    tracked_ids = set(names)

    def issue(uid: int, day: date | None = None, detail: str | None = None) -> dict:
        return {
            "user_id": uid,
            "full_name": names.get(uid, f"#{uid}"),
            "date": day,
            "detail": detail,
        }

    with_weekly = set(await db.scalars(select(WorkScheduleWeekly.user_id).distinct()))
    with_override = set(
        await db.scalars(
            select(WorkScheduleOverride.user_id)
            .where(WorkScheduleOverride.date >= date_from, WorkScheduleOverride.date <= date_to)
            .distinct()
        )
    )
    no_schedule = [
        issue(u.id, detail="Ish jadvali belgilanmagan — default Du–Ju 09:00–18:00 qo'llanadi")
        for u in users
        if u.id not in with_weekly and u.id not in with_override
    ]

    today = today_local()
    rows = list(
        await db.scalars(
            select(Attendance).where(Attendance.date >= date_from, Attendance.date <= date_to)
        )
    )
    open_checkouts = [
        issue(a.user_id, a.date, "«Ketdim» bosilmagan")
        for a in rows
        if a.user_id in tracked_ids
        and a.date < today
        and a.check_in_time is not None
        and a.check_out_time is None
    ]
    auto_closed = [
        issue(a.user_id, a.date, "Avtomatik yopilgan — ishlangan vaqt taxminiy")
        for a in rows
        if a.user_id in tracked_ids and a.note and AUTO_CLOSED_MARK in a.note
    ]

    pending_excused = [
        issue(e.user_id, e.date, e.reason[:120] if e.reason else None)
        for e in await db.scalars(
            select(ExcusedDay).where(
                ExcusedDay.date >= date_from,
                ExcusedDay.date <= date_to,
                ExcusedDay.status == ExcusedStatus.pending.value,
            )
        )
        if e.user_id in tracked_ids
    ]

    no_face = [
        issue(u.id, detail="Yuz ro'yxatdan o'tmagan — check-in qila olmaydi")
        for u in users
        if not u.has_face
    ]

    groups = (no_schedule, open_checkouts, auto_closed, pending_excused, no_face)
    return {
        "date_from": date_from,
        "date_to": date_to,
        "ok": not any(groups),
        "no_schedule": no_schedule,
        "open_checkouts": open_checkouts,
        "auto_closed": auto_closed,
        "pending_excused": pending_excused,
        "no_face": no_face,
    }


async def perform_check_in(
    db: AsyncSession,
    user: User,
    lat: float | None,
    lng: float | None,
    descriptor: list[float] | None = None,
    liveness: float = 0.0,
    accuracy: float | None = None,
) -> Attendance:
    """Xodimni bugungi kunga «Keldim» qiladi. Yuz (Face ID) tasdiqlangan va GPS ofis
    radiusida bo'lishi shart. Kechikish o'sha kungi ish oynasi boshlanishidan
    (grace bilan) hisoblanadi."""
    # 3.4-band qo'shimcha savoli: Boshliq davomat tizimining HECH bir qismida
    # (dashboard, statistika, digest, jadval) hisobga olinmaydi — shu izchillikni
    # saqlash uchun check-in ham bloklanadi. Aks holda "yozuv bor-u, hech qayerda
    # ko'rinmaydi" degan chalkash holat paydo bo'lardi.
    if user.role not in ATTENDANCE_TRACKED_ROLES:
        raise CheckError("Boshliq roli uchun davomat kuzatuvi yoqilmagan.")
    day = today_local()
    is_working, start, end = await _effective_today(db, user, day)

    _validate_face(user, descriptor, liveness)
    dist = await _validate_location(db, lat, lng, accuracy, user)

    # 5.1-band: tasdiqlangan sababli kun bo'lsa, kelgan bo'lsa ham kechikish
    # YOZILMAYDI. Ilgari `ExcusedDay` bu funksiyada IMPORT ham qilinmagan edi —
    # shifokordan keyin tushdan keyin kelgan xodim `late_minutes=120` bilan
    # yozilib, late-stats/employee-summary hisobotlariga kirar, digestda esa
    # "sababli" ro'yxatiga tushmasdi (u yerda faqat check-in YO'Q holat).
    # DIQQAT: bu so'rov `db.add(att)`dan OLDIN turishi SHART — aks holda
    # SQLAlchemy avtoflashi pending INSERT'ni try/except IntegrityError
    # (pastda) TASHQARISIDA flash qilib, 2.3-band tuzatishini buzib qo'yadi
    # (parallel check-in yana 500 qaytarardi).
    excused = await is_excused_day(db, user.id, day)

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

    if is_working and start and not excused:
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

    _apply_status(att, is_working, excused)
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
    lat: float | None,
    lng: float | None,
    descriptor: list[float] | None = None,
    liveness: float = 0.0,
    accuracy: float | None = None,
) -> Attendance:
    """Xodimni «Ketdim» qiladi. GPS + yuz tasdiqlanadi. Erta ketish ish oynasi
    tugashidan, ishlangan vaqt check-in/out orasidan hisoblanadi."""
    if user.role not in ATTENDANCE_TRACKED_ROLES:
        raise CheckError("Boshliq roli uchun davomat kuzatuvi yoqilmagan.")
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
    # 5.1-band: yozuvning O'Z sanasi bo'yicha (perform_check_in bilan bir xil).
    excused = await is_excused_day(db, user.id, att.date)

    _validate_face(user, descriptor, liveness)
    await _validate_location(db, lat, lng, accuracy, user)

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
        if is_working and end and not excused:
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

    status = (
        AttendanceStatus.weekend.value
        if not is_working
        else AttendanceStatus.excused.value
        if excused
        else (AttendanceStatus.late.value if att.late_minutes > 0 else AttendanceStatus.present.value)
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
