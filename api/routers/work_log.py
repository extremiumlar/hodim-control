"""Ish kundaligi — xodimning kunlik ish yozuvlari (KUNDALIK_ETIROZ_REJASI.md, Bosqich 1).

Xodim kun davomida bajargan ishlarini qisqa yozuvlar bilan qayd etadi (bot yoki
kabinet), rahbar oy kesimida ko'radi. Uch qat'iy qoida:

1. Yozuv HAR DOIM bugungi (Toshkent) kunga tushadi va faqat o'sha kuni
   tahrirlanadi/o'chiriladi — ertasi kundan hujjat (mijoz sanani yubormaydi).
2. O'chirish yumshoq (`deleted_at`) — barcha o'qishlar `deleted_at IS NULL`.
3. Pul mantig'iga ULANMAYDI — yozmaganlik jarima keltirmaydi, faqat qamrov
   hisobotida ko'rinadi.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user, get_db, require_roles, verify_bot_secret
from api.notify import notify_user
from api.schemas import (
    WorkLogBotCreate,
    WorkLogCoverageOut,
    WorkLogCoverageRow,
    WorkLogDayOut,
    WorkLogEntryOut,
    WorkLogMeCreate,
    WorkLogMePatch,
    WorkLogMonthOut,
    WorkLogReminderTick,
)
from api.services.attendance import is_excused_day
from api.services.attendance_month import build_month_cells, parse_month
from api.services.push import Category
from api.timeutil import TASHKENT_TZ, today_local
from db.models import (
    Attendance,
    AttendanceReminder,
    Role,
    User,
    WorkLogEntry,
    WorkLogSource,
)

router = APIRouter(prefix="/work-log", tags=["work-log"])

# Kundalikni KO'RADIGAN rahbarlar (8-bo'lim, savol 5 QAROR — defaultlar bilan).
# ROP kiradi, lekin faqat o'z jamoasi bilan cheklanadi (excused_days'dagi
# maxfiylik qoidasi: `User.manager_id` bo'yicha).
VIEW_ROLES = (Role.hr.value, Role.rop.value, Role.boss.value, Role.dasturchi.value)

# Eslatma izi mavjud attendance_reminders jadvaliga tushadi (UNIQUE
# user+date+kind) — yangi jadval kerak emas, idempotentlik tayyor.
REMINDER_KIND = "work_log"

# Eslatma oynasi: ish tugashiga 30 daqiqa qolganda ochiladi va ish tugagach
# yana 2 soat ochiq turadi (cron uzoq to'xtab qolsa ham eslatma kech bo'lsa-da
# boradi; undan keyin — bezovta qilmaymiz, baribir UNIQUE iz kuniga bittasini
# kafolatlaydi). 8-bo'lim savol 6 QAROR — default 30 daqiqa.
REMIND_BEFORE_END_MIN = 30
REMIND_UNTIL_AFTER_END_MIN = 120


def _to_out(e: WorkLogEntry) -> WorkLogEntryOut:
    return WorkLogEntryOut(
        id=e.id,
        user_id=e.user_id,
        date=e.date,
        text=e.text,
        source=e.source,
        created_at=e.created_at,
        updated_at=e.updated_at,
        editable=e.date == today_local(),
    )


async def _add_entry_for_user(
    db: AsyncSession, user: User, text: str, source: str
) -> WorkLogEntryOut:
    """Bot va web adapterlari SHU yordamchiga boradi (excused_days naqshi).
    Sana mijozdan OLINMAYDI — har doim bugungi (Toshkent) kun."""
    entry = WorkLogEntry(
        user_id=user.id, date=today_local(), text=text.strip(), source=source
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return _to_out(entry)


async def _get_own_editable_entry(
    db: AsyncSession, user: User, entry_id: int
) -> WorkLogEntry:
    """Tahrir/o'chirish uchun umumiy qo'riqchi: egalik + yumshoq o'chirilmagan +
    QULF (faqat bugungi yozuv). 404/403 farqi ataylab: begona yozuvga 404 —
    yozuv mavjudligi ham oshkor bo'lmasin."""
    entry = await db.get(WorkLogEntry, entry_id)
    if entry is None or entry.deleted_at is not None or entry.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Yozuv topilmadi")
    if entry.date != today_local():
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Yozuv qulflangan — faqat o'sha kunning o'zida o'zgartirish mumkin.",
        )
    return entry


async def _month_view(db: AsyncSession, target: User, month: str | None) -> WorkLogMonthOut:
    """Bir xodimning oylik kundaligi. Kunlarning "ish kunimi" belgisi
    `build_month_cells`dan — davomat kalendari bilan AYNAN bir qoida
    (override > haftalik > default), ikkinchi nusxa qilinmaydi."""
    try:
        first, last = parse_month(month)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Oy formati noto'g'ri (YYYY-MM)")

    cells = (await build_month_cells(db, [target], first, last))[target.id]["cells"]

    entries = list(
        await db.scalars(
            select(WorkLogEntry)
            .where(
                WorkLogEntry.user_id == target.id,
                WorkLogEntry.date >= first,
                WorkLogEntry.date <= last,
                WorkLogEntry.deleted_at.is_(None),
            )
            .order_by(WorkLogEntry.created_at.asc())
        )
    )
    by_day: dict[str, list[WorkLogEntryOut]] = {}
    for e in entries:
        by_day.setdefault(e.date.isoformat(), []).append(_to_out(e))

    today = today_local()
    days: list[WorkLogDayOut] = []
    work_days = 0
    logged_days = 0
    for cell in cells:
        day_iso = cell["date"]
        is_working = cell["schedule_start"] is not None
        day_entries = by_day.get(day_iso, [])
        # Qamrov faqat O'TGAN (bugungacha) ish kunlari bo'yicha — kelajak
        # kunlar "yozilmagan" deb hisoblanmasin.
        if is_working and day_iso <= today.isoformat():
            work_days += 1
            if day_entries:
                logged_days += 1
        days.append(
            WorkLogDayOut(date=day_iso, is_working=is_working, entries=day_entries)
        )

    return WorkLogMonthOut(
        month=first.strftime("%Y-%m"),
        user_id=target.id,
        user_full_name=target.full_name,
        days=days,
        work_days=work_days,
        logged_days=logged_days,
        entries_count=len(entries),
    )


# ─── Xodim: bot adapterlari (X-Bot-Secret, shaxs = telegram_id) ─────────────────


@router.post("/bot", response_model=WorkLogEntryOut, dependencies=[Depends(verify_bot_secret)])
async def add_entry_bot(payload: WorkLogBotCreate, db: AsyncSession = Depends(get_db)) -> WorkLogEntryOut:
    user = await db.scalar(select(User).where(User.telegram_id == payload.telegram_id))
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Foydalanuvchi topilmadi")
    return await _add_entry_for_user(db, user, payload.text, WorkLogSource.bot.value)


@router.get(
    "/bot/today/{telegram_id}",
    response_model=list[WorkLogEntryOut],
    dependencies=[Depends(verify_bot_secret)],
)
async def today_entries_bot(telegram_id: int, db: AsyncSession = Depends(get_db)) -> list[WorkLogEntryOut]:
    """Bot «📝 Ish kundaligi» tugmasi bosilganda bugungi yozuvlarni ko'rsatadi."""
    user = await db.scalar(select(User).where(User.telegram_id == telegram_id))
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Foydalanuvchi topilmadi")
    entries = list(
        await db.scalars(
            select(WorkLogEntry)
            .where(
                WorkLogEntry.user_id == user.id,
                WorkLogEntry.date == today_local(),
                WorkLogEntry.deleted_at.is_(None),
            )
            .order_by(WorkLogEntry.created_at.asc())
        )
    )
    return [_to_out(e) for e in entries]


# ─── Xodim: web/mobil (JWT, shaxs = token) ──────────────────────────────────────


@router.get("/me", response_model=WorkLogMonthOut)
async def my_month(
    month: str | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WorkLogMonthOut:
    return await _month_view(db, user, month)


@router.post("/me", response_model=WorkLogEntryOut)
async def add_my_entry(
    payload: WorkLogMeCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WorkLogEntryOut:
    """Sxema ATAYLAB boshqa (`WorkLogMeCreate`): unda `telegram_id` YO'Q,
    shaxs tokendan — mijoz boshqa birov nomidan yoza olmaydi."""
    return await _add_entry_for_user(db, user, payload.text, WorkLogSource.web.value)


@router.patch("/me/{entry_id}", response_model=WorkLogEntryOut)
async def edit_my_entry(
    entry_id: int,
    payload: WorkLogMePatch,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WorkLogEntryOut:
    entry = await _get_own_editable_entry(db, user, entry_id)
    entry.text = payload.text.strip()
    entry.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(entry)
    return _to_out(entry)


@router.delete("/me/{entry_id}")
async def delete_my_entry(
    entry_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Yumshoq o'chirish (Norm naqshi) — qator qoladi, o'qishlardan yo'qoladi."""
    entry = await _get_own_editable_entry(db, user, entry_id)
    entry.deleted_at = datetime.utcnow()
    await db.commit()
    return {"deleted": True}


# ─── Rahbar (JWT) ───────────────────────────────────────────────────────────────


@router.get("/coverage", response_model=WorkLogCoverageOut)
async def coverage(
    month: str | None = None,
    actor: User = Depends(require_roles(*VIEW_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> WorkLogCoverageOut:
    """Oy kesimida barcha xodim: nechta ish kunidan nechtasida yozuv bor.
    DIQQAT: `/coverage` literal yo'li — parametrli yo'llardan oldin e'lon
    qilingan bo'lishi shart emas (bu routerda GET catch-all yo'q), lekin
    payroll.py:676 saboqlari uchun baribir yuqorida turadi."""
    try:
        first, last = parse_month(month)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Oy formati noto'g'ri (YYYY-MM)")

    query = (
        select(User)
        .where(User.role == Role.employee.value, User.is_active == True)  # noqa: E712
        .order_by(User.full_name)
    )
    # Maxfiylik (excused_days list_excused_days bilan bir qoida): ROP faqat
    # o'z jamoasini ko'radi.
    if actor.role == Role.rop.value:
        query = query.where(User.manager_id == actor.id)
    users = list(await db.scalars(query))
    if not users:
        return WorkLogCoverageOut(month=first.strftime("%Y-%m"), rows=[])

    cells_by_user = await build_month_cells(db, users, first, last)

    # Bitta bulk so'rov: (user_id, date) -> yozuvlar soni (N+1 emas).
    rows = await db.execute(
        select(WorkLogEntry.user_id, WorkLogEntry.date, func.count(WorkLogEntry.id))
        .where(
            WorkLogEntry.user_id.in_([u.id for u in users]),
            WorkLogEntry.date >= first,
            WorkLogEntry.date <= last,
            WorkLogEntry.deleted_at.is_(None),
        )
        .group_by(WorkLogEntry.user_id, WorkLogEntry.date)
    )
    count_by_user_day: dict[tuple[int, str], int] = {
        (uid, d.isoformat()): n for uid, d, n in rows
    }

    today_iso = today_local().isoformat()
    out_rows: list[WorkLogCoverageRow] = []
    for u in users:
        work_days = 0
        logged_days = 0
        entries_count = 0
        for cell in cells_by_user[u.id]["cells"]:
            n = count_by_user_day.get((u.id, cell["date"]), 0)
            entries_count += n
            if cell["schedule_start"] is not None and cell["date"] <= today_iso:
                work_days += 1
                if n:
                    logged_days += 1
        out_rows.append(
            WorkLogCoverageRow(
                user_id=u.id,
                full_name=u.full_name,
                work_days=work_days,
                logged_days=logged_days,
                entries_count=entries_count,
            )
        )
    return WorkLogCoverageOut(month=first.strftime("%Y-%m"), rows=out_rows)


@router.get("", response_model=WorkLogMonthOut)
async def user_month(
    user_id: int,
    month: str | None = None,
    actor: User = Depends(require_roles(*VIEW_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> WorkLogMonthOut:
    """Bitta xodimning oylik kundaligi (rahbar ko'rinishi)."""
    target = await db.get(User, user_id)
    if not target:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Xodim topilmadi")
    if actor.role == Role.rop.value and target.manager_id != actor.id and target.id != actor.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Faqat o'z jamoangizni ko'ra olasiz")
    return await _month_view(db, target, month)


# ─── Kechki eslatma (scheduler) ─────────────────────────────────────────────────


@router.post("/reminder-tick", dependencies=[Depends(verify_bot_secret)])
async def work_log_reminder_tick(
    payload: WorkLogReminderTick, db: AsyncSession = Depends(get_db)
) -> dict:
    """«Bugun kundalikka hech narsa yozmadingiz» — ish tugashiga yaqin,
    bugun ishlagan va hali yozmagan xodimlarga.

    Mantiq `api/services/cron_jobs.py` da — cPanel cron uni SAYTGA so'rov
    yubormasdan, o'z jarayonida bajaradi (SAYT_QOTISHI_TAHLIL.md Bosqich 4b
    naqshi). Bu endpoint Docker/scheduler rejimi va qo'lda `dry_run`
    tekshiruvi uchun saqlanadi."""
    from api.services.cron_jobs import work_log_reminder_tick as _tick

    return await _tick(db, dry_run=payload.dry_run)
