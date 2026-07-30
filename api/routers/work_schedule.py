from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user, get_db, verify_bot_secret
from api.routers.hourly_plan import DEFAULT_END, DEFAULT_START
from api.services.attendance import ATTENDANCE_TRACKED_ROLES, recompute_attendance
from api.timeutil import today_local
from api.schemas import (
    EffectiveDay,
    WorkDayEntry,
    WorkOverrideIn,
    WorkOverrideOut,
    WorkWeeklyIn,
    WorkWeeklyOut,
    WorkWeekOut,
)
from db.models import AuditLog, Attendance, Role, User, WorkScheduleOverride, WorkScheduleWeekly

router = APIRouter(prefix="/work-schedule", tags=["work-schedule"])

MANAGER_ROLES = (Role.hr.value, Role.rop.value, Role.boss.value, Role.dasturchi.value)


def _require_manager(user: User = Depends(get_current_user)) -> User:
    if user.role not in MANAGER_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Bu amal faqat rahbarlar uchun")
    return user


async def _get_user_or_404(db: AsyncSession, user_id: int) -> User:
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Foydalanuvchi topilmadi")
    return user


async def _get_manageable_user_or_404(db: AsyncSession, user_id: int, actor: User) -> User:
    """Norma boshqarish bilan bir xil doira: Boshliq/Dasturchi — hammaga; ROP/HR —
    faqat can_manage_norms ruxsat bergan xodimlarga ish jadvalini o'zgartira oladi."""
    from api.routers.norms import can_manage_norms  # circular importdan qochish

    user = await _get_user_or_404(db, user_id)
    if actor.role in (Role.boss.value, Role.dasturchi.value):
        return user
    if not can_manage_norms(actor, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Bu xodim sizning nazoratingizda emas")
    return user


def _week_start(d: date) -> date:
    """Sanani o'z ichiga olgan haftaning dushanbasi."""
    return d - timedelta(days=d.weekday())


async def _recalc_from(db: AsyncSession, user: User, from_day: date) -> None:
    """3.1-band: ish jadvali o'zgarganda, O'SHA XODIMNING allaqachon mavjud
    (check-in qilingan) yozuvlarini — BUGUNGI va KELAJAKDAGI (`from_day`dan
    boshlab) — yangi jadvalga qarab qayta hisoblaydi. O'TGAN kunlarga
    TEGILMAYDI — tarix o'zgarmas qoladi.

    Nima uchun kerak edi: xodim 09:30 da keldi (late=25 yozildi), rahbar
    startni 10:00 ga o'zgartirdi — baza eski (25) qiymatda qolib, guruh
    digesti esa JORIY jadvaldan hisoblab bir odamni bir vaqtning o'zida ham
    "kechikkan", ham "erta kelgan" deb ko'rsatardi."""
    rows = list(
        await db.scalars(
            select(Attendance).where(Attendance.user_id == user.id, Attendance.date >= from_day)
        )
    )
    if not rows:
        return
    for att in rows:
        if att.check_in_time is None:
            continue  # hech narsa yozilmagan kun — qayta hisoblashning ma'nosi yo'q
        await recompute_attendance(db, att, user)
    await db.commit()


async def _effective_week(db: AsyncSession, user: User, start: date) -> WorkWeekOut:
    """Dushanbadan boshlab 7 kunning amaldagi jadvali: override > haftalik andoza > unset."""
    week_start = _week_start(start)
    week_end = week_start + timedelta(days=6)

    weekly = {
        w.weekday: w
        for w in await db.scalars(select(WorkScheduleWeekly).where(WorkScheduleWeekly.user_id == user.id))
    }
    overrides = {
        o.date: o
        for o in await db.scalars(
            select(WorkScheduleOverride).where(
                WorkScheduleOverride.user_id == user.id,
                WorkScheduleOverride.date >= week_start,
                WorkScheduleOverride.date <= week_end,
            )
        )
    }

    days: list[EffectiveDay] = []
    for i in range(7):
        d = week_start + timedelta(days=i)
        ov = overrides.get(d)
        if ov is not None:
            days.append(
                EffectiveDay(
                    date=d, weekday=d.weekday(), is_working=ov.is_working,
                    start_time=ov.start_time, end_time=ov.end_time, source="override", note=ov.note,
                )
            )
            continue
        w = weekly.get(d.weekday())
        if w is not None:
            days.append(
                EffectiveDay(
                    date=d, weekday=d.weekday(), is_working=w.is_working,
                    start_time=w.start_time, end_time=w.end_time, source="weekly",
                )
            )
        else:
            # Jadval umuman belgilanmagan — dushanba-jumada default ish kuni,
            # shanba-yakshanbada dam olish kuni deb hisoblanadi (hourly_plan bilan
            # bir xil qoida: api/routers/hourly_plan.py _effective_today).
            days.append(
                EffectiveDay(
                    date=d, weekday=d.weekday(), is_working=d.weekday() < 5,
                    start_time=None, end_time=None, source="unset",
                )
            )
    return WorkWeekOut(user_id=user.id, user_full_name=user.full_name, days=days)


def _build_week(user: User, weekly: dict, overrides: dict, week_start: date) -> WorkWeekOut:
    """`_effective_week`ning bitta xodim uchun sof (so'rovsiz) versiyasi — 3.5-band:
    `all_week` barcha xodimlar uchun oldindan BITTA so'rovda olingan `weekly`/
    `overrides` lug'atlaridan foydalanadi, har biriga alohida murojaat qilmaydi."""
    days: list[EffectiveDay] = []
    for i in range(7):
        d = week_start + timedelta(days=i)
        ov = overrides.get((user.id, d))
        if ov is not None:
            days.append(
                EffectiveDay(
                    date=d, weekday=d.weekday(), is_working=ov.is_working,
                    start_time=ov.start_time, end_time=ov.end_time, source="override", note=ov.note,
                )
            )
            continue
        w = weekly.get((user.id, d.weekday()))
        if w is not None:
            days.append(
                EffectiveDay(
                    date=d, weekday=d.weekday(), is_working=w.is_working,
                    start_time=w.start_time, end_time=w.end_time, source="weekly",
                )
            )
        else:
            days.append(
                EffectiveDay(
                    date=d, weekday=d.weekday(), is_working=d.weekday() < 5,
                    start_time=None, end_time=None, source="unset",
                )
            )
    return WorkWeekOut(user_id=user.id, user_full_name=user.full_name, days=days)


# --- Web (rahbarlar) — haftalik andoza ---


@router.get("/{user_id}/weekly", response_model=WorkWeeklyOut)
async def get_weekly(
    user_id: int, actor: User = Depends(_require_manager), db: AsyncSession = Depends(get_db)
) -> WorkWeeklyOut:
    user = await _get_manageable_user_or_404(db, user_id, actor)
    stored = {
        w.weekday: w
        for w in await db.scalars(select(WorkScheduleWeekly).where(WorkScheduleWeekly.user_id == user_id))
    }
    # Saqlanmagan kunlar uchun AMALDAGI defaultni qaytaramiz (Du-Ju 09:00-18:00,
    # Sha/Yak dam) — `hourly_plan._effective_today` va davomat kechikish hisobi
    # aynan shundan foydalanadi. Ilgari bu yerda "hamma kun is_working=True,
    # vaqtsiz" qaytarilardi: rahbar tahrirlash oynasida yakshanbani ham ish kuni
    # deb ko'rar, saqlasa esa xodimga haqiqatan shanba-yakshanba ish kuni bo'lib
    # yozilib ketardi (davomat esa boshqacha hisoblardi).
    days = [
        WorkDayEntry(
            weekday=wd,
            is_working=stored[wd].is_working if wd in stored else wd < 5,
            start_time=(
                stored[wd].start_time if wd in stored else (DEFAULT_START if wd < 5 else None)
            ),
            end_time=(stored[wd].end_time if wd in stored else (DEFAULT_END if wd < 5 else None)),
        )
        for wd in range(7)
    ]
    return WorkWeeklyOut(user_id=user.id, user_full_name=user.full_name, days=days)


@router.put("/{user_id}/weekly", response_model=WorkWeeklyOut)
async def set_weekly(
    user_id: int, payload: WorkWeeklyIn, actor: User = Depends(_require_manager), db: AsyncSession = Depends(get_db)
) -> WorkWeeklyOut:
    user = await _get_manageable_user_or_404(db, user_id, actor)
    seen_weekdays: set[int] = set()
    for entry in payload.days:
        if entry.weekday in seen_weekdays:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Hafta kuni takrorlangan: {entry.weekday}")
        seen_weekdays.add(entry.weekday)
        if entry.is_working and (entry.start_time is None or entry.end_time is None):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ish kuni uchun boshlanish va tugash vaqti kerak")
        if entry.start_time and entry.end_time and entry.start_time >= entry.end_time:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Tugash vaqti boshlanishdan keyin bo'lishi kerak")

    # 5.11-band: `AuditLog` ilgari IMPORT ham qilinmagan edi — jadval "eski
    # holatni DELETE qilib qayta yozish" bilan almashtirilardi va ROP/HR
    # bugungi kunga qulay vaqt qo'yib, kechikishni "yo'qotib yuborsa" ham
    # HECH QAYERDA iz qolmasdi. Eski holat o'chirishdan OLDIN saqlanadi.
    before_rows = list(
        await db.scalars(
            select(WorkScheduleWeekly).where(WorkScheduleWeekly.user_id == user_id).order_by(WorkScheduleWeekly.weekday)
        )
    )
    before = [
        {"weekday": w.weekday, "is_working": w.is_working, "start_time": w.start_time, "end_time": w.end_time}
        for w in before_rows
    ]

    await db.execute(delete(WorkScheduleWeekly).where(WorkScheduleWeekly.user_id == user_id))
    for entry in payload.days:
        db.add(
            WorkScheduleWeekly(
                user_id=user_id,
                weekday=entry.weekday,
                is_working=entry.is_working,
                start_time=entry.start_time if entry.is_working else None,
                end_time=entry.end_time if entry.is_working else None,
            )
        )
    db.add(
        AuditLog(
            actor_id=actor.id,
            action="work_schedule_weekly_changed",
            target_user_id=user_id,
            before={"days": before} if before else None,
            after={
                "days": [
                    {"weekday": e.weekday, "is_working": e.is_working, "start_time": e.start_time, "end_time": e.end_time}
                    for e in payload.days
                ]
            },
        )
    )
    await db.commit()
    await _recalc_from(db, user, today_local())
    return await get_weekly(user_id, actor, db)


# --- Web (rahbarlar) — aniq sana o'zgartirishlari ---


@router.get("/{user_id}/overrides", response_model=list[WorkOverrideOut])
async def list_overrides(
    user_id: int,
    date_from: date | None = None,
    date_to: date | None = None,
    actor: User = Depends(_require_manager),
    db: AsyncSession = Depends(get_db),
) -> list[WorkScheduleOverride]:
    await _get_manageable_user_or_404(db, user_id, actor)
    q = select(WorkScheduleOverride).where(WorkScheduleOverride.user_id == user_id)
    if date_from:
        q = q.where(WorkScheduleOverride.date >= date_from)
    if date_to:
        q = q.where(WorkScheduleOverride.date <= date_to)
    return list(await db.scalars(q.order_by(WorkScheduleOverride.date)))


@router.put("/{user_id}/override", response_model=WorkOverrideOut)
async def set_override(
    user_id: int, payload: WorkOverrideIn, actor: User = Depends(_require_manager), db: AsyncSession = Depends(get_db)
) -> WorkScheduleOverride:
    user = await _get_manageable_user_or_404(db, user_id, actor)
    if payload.is_working and (payload.start_time is None or payload.end_time is None):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ish kuni uchun boshlanish va tugash vaqti kerak")
    if payload.start_time and payload.end_time and payload.start_time >= payload.end_time:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Tugash vaqti boshlanishdan keyin bo'lishi kerak")

    existing = await db.scalar(
        select(WorkScheduleOverride).where(
            WorkScheduleOverride.user_id == user_id, WorkScheduleOverride.date == payload.date
        )
    )
    # 5.11-band: ish jadvali kechikish hisobining yagona asosi — ROP/HR o'z
    # doirasidagi xodimga bugungi sanaga qulay vaqt qo'yib, kechikishni "yo'qotib
    # yuborishi" mumkin edi va bu HECH QAYERDA (audit) qayd etilmasdi.
    before = (
        {
            "is_working": existing.is_working,
            "start_time": existing.start_time,
            "end_time": existing.end_time,
            "note": existing.note,
        }
        if existing is not None
        else None
    )
    if existing is None:
        existing = WorkScheduleOverride(user_id=user_id, date=payload.date)
        db.add(existing)
    existing.is_working = payload.is_working
    existing.start_time = payload.start_time if payload.is_working else None
    existing.end_time = payload.end_time if payload.is_working else None
    existing.note = payload.note
    db.add(
        AuditLog(
            actor_id=actor.id,
            action="work_schedule_override_changed",
            target_user_id=user_id,
            before=before,
            after={
                "date": payload.date.isoformat(),
                "is_working": payload.is_working,
                "start_time": payload.start_time,
                "end_time": payload.end_time,
                "note": payload.note,
            },
        )
    )
    await db.commit()
    await db.refresh(existing)
    # 3.1-band: faqat BUGUNGI yoki KELAJAKDAGI sana uchun qayta hisoblaymiz —
    # o'tgan kunga override qo'yish (masalan orqaga qarab sababli kun belgilash)
    # tarixni o'zgartirmasligi kerak. Faqat SHU sanaga tegishli — boshqa kunlar
    # bu override'dan ta'sirlanmaydi.
    if payload.date >= today_local():
        att = await db.scalar(
            select(Attendance).where(Attendance.user_id == user_id, Attendance.date == payload.date)
        )
        if att is not None and att.check_in_time is not None:
            await recompute_attendance(db, att, user)
            await db.commit()
    return existing


@router.delete("/{user_id}/override/{day}")
async def delete_override(
    user_id: int, day: date, actor: User = Depends(_require_manager), db: AsyncSession = Depends(get_db)
) -> dict:
    await _get_manageable_user_or_404(db, user_id, actor)
    existing = await db.scalar(
        select(WorkScheduleOverride).where(
            WorkScheduleOverride.user_id == user_id, WorkScheduleOverride.date == day
        )
    )
    if existing is not None:
        db.add(
            AuditLog(
                actor_id=actor.id,
                action="work_schedule_override_deleted",
                target_user_id=user_id,
                before={
                    "date": day.isoformat(),
                    "is_working": existing.is_working,
                    "start_time": existing.start_time,
                    "end_time": existing.end_time,
                    "note": existing.note,
                },
                after=None,
            )
        )
    await db.execute(
        delete(WorkScheduleOverride).where(
            WorkScheduleOverride.user_id == user_id, WorkScheduleOverride.date == day
        )
    )
    await db.commit()
    return {"deleted": True}


# --- Bot — xodim o'z jadvalini, rahbar hammani ko'radi ---


@router.get("/{telegram_id}/me/week", response_model=WorkWeekOut, dependencies=[Depends(verify_bot_secret)])
async def my_week(
    telegram_id: int, start: date | None = None, db: AsyncSession = Depends(get_db)
) -> WorkWeekOut:
    """Xodimning O'Z haftalik amaldagi jadvali (start — hafta ichidagi istalgan sana)."""
    user = await db.scalar(select(User).where(User.telegram_id == telegram_id))
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Foydalanuvchi topilmadi")
    # date.today() server (UTC) sanasini olardi — yarim tunda noto'g'ri hafta chiqardi
    return await _effective_week(db, user, start or today_local())


@router.get("/me/week", response_model=WorkWeekOut)
async def my_week_web(
    start: date | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WorkWeekOut:
    """Web/mobil (JWT) versiyasi — xodim kabineti uchun. Yuqoridagi bot
    endpointi bilan AYNAN bir xil mantiqni (`_effective_week`) chaqiradi, farqi
    faqat shaxsni aniqlashda: bot `telegram_id`dan yechadi, bu esa TOKENDAN
    oladi (path'da user_id yo'q — xodim boshqa birovning jadvalini so'ray
    olmasligi uchun). Naqsh: payroll.py `/me/late-status`.

    Marshrut to'qnashuvi yo'q: qolgan 2-segmentli yo'llarning ikkinchi qismi
    boshqa (`weekly`, `overrides`, `override`)."""
    return await _effective_week(db, user, start or today_local())


@router.get("/{telegram_id}/all/week", response_model=list[WorkWeekOut], dependencies=[Depends(verify_bot_secret)])
async def all_week(
    telegram_id: int, start: date | None = None, db: AsyncSession = Depends(get_db)
) -> list[WorkWeekOut]:
    """Rahbar uchun: davomat kuzatiladigan barcha faol xodimlarning (Boshliqdan
    tashqari — ATTENDANCE_TRACKED_ROLES) haftalik jadvali. Jadval davomat
    kechikishini hisoblashda ishlatilgani uchun ro'yxat davomat qamrovi bilan
    bir xil bo'lishi shart.

    3.5-band: ilgari har xodim uchun `_effective_week` alohida chaqirilardi —
    2 ta so'rov (weekly + override) xodimlar soniga ko'paytirilardi (N+1).
    `digest_tick` har daqiqa ishlagani uchun bu sezilarli yuk edi. Endi hamma
    xodim uchun weekly/override BITTA so'rovda olinib, lug'atga solinadi."""
    actor = await db.scalar(select(User).where(User.telegram_id == telegram_id))
    if not actor or actor.role not in MANAGER_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Bu amal faqat rahbarlar uchun")
    users = list(
        await db.scalars(
            select(User)
            .where(User.is_active == True, User.role.in_(ATTENDANCE_TRACKED_ROLES))  # noqa: E712
            .order_by(User.full_name)
        )
    )
    if not users:
        return []
    user_ids = [u.id for u in users]
    week_start = _week_start(start or today_local())
    week_end = week_start + timedelta(days=6)

    weekly = {
        (w.user_id, w.weekday): w
        for w in await db.scalars(
            select(WorkScheduleWeekly).where(WorkScheduleWeekly.user_id.in_(user_ids))
        )
    }
    overrides = {
        (o.user_id, o.date): o
        for o in await db.scalars(
            select(WorkScheduleOverride).where(
                WorkScheduleOverride.user_id.in_(user_ids),
                WorkScheduleOverride.date >= week_start,
                WorkScheduleOverride.date <= week_end,
            )
        )
    }
    return [_build_week(u, weekly, overrides, week_start) for u in users]
