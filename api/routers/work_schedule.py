from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user, get_db, verify_bot_secret
from api.schemas import (
    EffectiveDay,
    WorkDayEntry,
    WorkOverrideIn,
    WorkOverrideOut,
    WorkWeeklyIn,
    WorkWeeklyOut,
    WorkWeekOut,
)
from db.models import Role, User, WorkScheduleOverride, WorkScheduleWeekly

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


def _week_start(d: date) -> date:
    """Sanani o'z ichiga olgan haftaning dushanbasi."""
    return d - timedelta(days=d.weekday())


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
            days.append(
                EffectiveDay(date=d, weekday=d.weekday(), is_working=True, start_time=None, end_time=None, source="unset")
            )
    return WorkWeekOut(user_id=user.id, user_full_name=user.full_name, days=days)


# --- Web (rahbarlar) — haftalik andoza ---


@router.get("/{user_id}/weekly", response_model=WorkWeeklyOut)
async def get_weekly(
    user_id: int, _: User = Depends(_require_manager), db: AsyncSession = Depends(get_db)
) -> WorkWeeklyOut:
    user = await _get_user_or_404(db, user_id)
    stored = {
        w.weekday: w
        for w in await db.scalars(select(WorkScheduleWeekly).where(WorkScheduleWeekly.user_id == user_id))
    }
    days = [
        WorkDayEntry(
            weekday=wd,
            is_working=stored[wd].is_working if wd in stored else True,
            start_time=stored[wd].start_time if wd in stored else None,
            end_time=stored[wd].end_time if wd in stored else None,
        )
        for wd in range(7)
    ]
    return WorkWeeklyOut(user_id=user.id, user_full_name=user.full_name, days=days)


@router.put("/{user_id}/weekly", response_model=WorkWeeklyOut)
async def set_weekly(
    user_id: int, payload: WorkWeeklyIn, _: User = Depends(_require_manager), db: AsyncSession = Depends(get_db)
) -> WorkWeeklyOut:
    user = await _get_user_or_404(db, user_id)
    for entry in payload.days:
        if entry.is_working and (entry.start_time is None or entry.end_time is None):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ish kuni uchun boshlanish va tugash vaqti kerak")
        if entry.start_time and entry.end_time and entry.start_time >= entry.end_time:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Tugash vaqti boshlanishdan keyin bo'lishi kerak")

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
    await db.commit()
    return await get_weekly(user_id, _, db)


# --- Web (rahbarlar) — aniq sana o'zgartirishlari ---


@router.get("/{user_id}/overrides", response_model=list[WorkOverrideOut])
async def list_overrides(
    user_id: int,
    date_from: date | None = None,
    date_to: date | None = None,
    _: User = Depends(_require_manager),
    db: AsyncSession = Depends(get_db),
) -> list[WorkScheduleOverride]:
    await _get_user_or_404(db, user_id)
    q = select(WorkScheduleOverride).where(WorkScheduleOverride.user_id == user_id)
    if date_from:
        q = q.where(WorkScheduleOverride.date >= date_from)
    if date_to:
        q = q.where(WorkScheduleOverride.date <= date_to)
    return list(await db.scalars(q.order_by(WorkScheduleOverride.date)))


@router.put("/{user_id}/override", response_model=WorkOverrideOut)
async def set_override(
    user_id: int, payload: WorkOverrideIn, _: User = Depends(_require_manager), db: AsyncSession = Depends(get_db)
) -> WorkScheduleOverride:
    await _get_user_or_404(db, user_id)
    if payload.is_working and (payload.start_time is None or payload.end_time is None):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ish kuni uchun boshlanish va tugash vaqti kerak")
    if payload.start_time and payload.end_time and payload.start_time >= payload.end_time:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Tugash vaqti boshlanishdan keyin bo'lishi kerak")

    existing = await db.scalar(
        select(WorkScheduleOverride).where(
            WorkScheduleOverride.user_id == user_id, WorkScheduleOverride.date == payload.date
        )
    )
    if existing is None:
        existing = WorkScheduleOverride(user_id=user_id, date=payload.date)
        db.add(existing)
    existing.is_working = payload.is_working
    existing.start_time = payload.start_time if payload.is_working else None
    existing.end_time = payload.end_time if payload.is_working else None
    existing.note = payload.note
    await db.commit()
    await db.refresh(existing)
    return existing


@router.delete("/{user_id}/override/{day}")
async def delete_override(
    user_id: int, day: date, _: User = Depends(_require_manager), db: AsyncSession = Depends(get_db)
) -> dict:
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
    return await _effective_week(db, user, start or date.today())


@router.get("/{telegram_id}/all/week", response_model=list[WorkWeekOut], dependencies=[Depends(verify_bot_secret)])
async def all_week(
    telegram_id: int, start: date | None = None, db: AsyncSession = Depends(get_db)
) -> list[WorkWeekOut]:
    """Rahbar uchun: barcha faol xodimlarning haftalik jadvali."""
    actor = await db.scalar(select(User).where(User.telegram_id == telegram_id))
    if not actor or actor.role not in MANAGER_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Bu amal faqat rahbarlar uchun")
    users = list(await db.scalars(select(User).where(User.is_active == True).order_by(User.full_name)))  # noqa: E712
    return [await _effective_week(db, u, start or date.today()) for u in users]
