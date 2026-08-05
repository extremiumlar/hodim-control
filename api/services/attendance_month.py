"""Oylik davomat kataklarini qurish — YAGONA hisoblash manbai (UX-A2/A3).

Ikki iste'molchi bor:
  - `GET /attendance/matrix?month=`      — rahbar: barcha xodim × kun to'ri;
  - `GET /attendance/me/history?month=`  — xodim: o'zining bitta qatori.

Ikkalasi shu moduldagi `build_month_cells` dan foydalanadi — "yozuvsiz kun
nima degani" (kelmaganmi, dam kunimi, sababli kunmi, kelajakmi) degan qoida
BITTA joyda turadi. Aks holda rahbar matritsasi bilan xodim kalendari bir
kunni ikki xil ko'rsatib qolardi.

Katak statusi qoidasi (DAVOMAT_UX_PROMPT.md 🅰 A2):
  1. Yozuv bor          → yozuv statusi (present/late/absent/weekend/excused).
  2. Yozuv yo'q, kelajak → future (jadval bo'yicha dam bo'lsa weekend).
  3. Yozuv yo'q, BUGUN, ish kuni → pending (kun hali tugamagan).
  4. Yozuv yo'q, o'tgan ish kuni → absent (virtual — kechki avtomatik yozish
     o'tkazib yuborgan bo'lishi mumkin); tasdiqlangan sababli kun → excused.
  5. Yozuv yo'q, dam kuni → weekend.

Samaradorlik: butun oy uchun 4 ta bulk so'rov (attendance, override, weekly,
excused) — xodim boshiga alohida so'rov QILINMAYDI (3.5-band saboqlari).
"""
from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.routers.hourly_plan import DEFAULT_END, DEFAULT_START
from api.services.attendance import AUTO_CLOSED_MARK
from api.timeutil import TASHKENT_TZ, today_local
from db.models import (
    Attendance,
    AttendanceStatus,
    ExcusedDay,
    ExcusedStatus,
    User,
    WorkScheduleOverride,
    WorkScheduleWeekly,
)


def parse_month(month: str | None) -> tuple[date, date]:
    """"YYYY-MM" → (oy boshi, oy oxiri). Bo'sh/None — joriy oy.
    Noto'g'ri format — ValueError (endpoint 400 ga aylantiradi)."""
    if not month:
        t = today_local()
        first = t.replace(day=1)
    else:
        y, m = month.split("-")
        first = date(int(y), int(m), 1)  # noto'g'ri qiymatda ValueError
    last = first.replace(day=calendar.monthrange(first.year, first.month)[1])
    return first, last


def _hm_local(dt_utc: datetime | None) -> str | None:
    """Bazadagi naive-UTC vaqt → mahalliy "HH:MM" (frontend TZ hisoblamasin)."""
    if dt_utc is None:
        return None
    return dt_utc.replace(tzinfo=timezone.utc).astimezone(TASHKENT_TZ).strftime("%H:%M")


async def build_month_cells(
    db: AsyncSession, users: list[User], first: date, last: date
) -> dict[int, dict]:
    """Har xodim uchun {user_id: {"cells": [...], "totals": {...}}}.

    Katak maydonlari:
      date, status, late_minutes, check_in, check_out, worked_minutes,
      schedule_start, schedule_end, note, flags[]
    flags: auto_closed (kechki avtomatik yopilgan), manual (qo'lda tuzatilgan),
    no_checkout ("Ketdim" bosilmagan ochiq kun).
    """
    user_ids = [u.id for u in users]
    today = today_local()

    att_by_user_day: dict[tuple[int, date], Attendance] = {
        (a.user_id, a.date): a
        for a in await db.scalars(
            select(Attendance).where(
                Attendance.user_id.in_(user_ids),
                Attendance.date >= first,
                Attendance.date <= last,
            )
        )
    }
    ov_by_user_day: dict[tuple[int, date], WorkScheduleOverride] = {
        (o.user_id, o.date): o
        for o in await db.scalars(
            select(WorkScheduleOverride).where(
                WorkScheduleOverride.user_id.in_(user_ids),
                WorkScheduleOverride.date >= first,
                WorkScheduleOverride.date <= last,
            )
        )
    }
    weekly_by_user_wd: dict[tuple[int, int], WorkScheduleWeekly] = {
        (w.user_id, w.weekday): w
        for w in await db.scalars(
            select(WorkScheduleWeekly).where(WorkScheduleWeekly.user_id.in_(user_ids))
        )
    }
    excused_days: set[tuple[int, date]] = {
        (e.user_id, e.date)
        for e in await db.scalars(
            select(ExcusedDay).where(
                ExcusedDay.user_id.in_(user_ids),
                ExcusedDay.date >= first,
                ExcusedDay.date <= last,
                ExcusedDay.status == ExcusedStatus.approved.value,
            )
        )
    }

    def schedule_for(uid: int, day: date) -> tuple[bool, str | None, str | None]:
        """(is_working, start, end) — override > haftalik > default.
        `hourly_plan._effective_today` bilan AYNAN bir qoida, lekin so'rovsiz
        (yuqoridagi bulk lug'atlardan)."""
        ov = ov_by_user_day.get((uid, day))
        if ov is not None:
            if not ov.is_working:
                return False, None, None
            return True, ov.start_time or DEFAULT_START, ov.end_time or DEFAULT_END
        w = weekly_by_user_wd.get((uid, day.weekday()))
        if w is not None:
            if not w.is_working:
                return False, None, None
            return True, w.start_time or DEFAULT_START, w.end_time or DEFAULT_END
        if day.weekday() < 5:
            return True, DEFAULT_START, DEFAULT_END
        return False, None, None

    out: dict[int, dict] = {}
    for u in users:
        cells: list[dict] = []
        t = {"present_days": 0, "late_count": 0, "late_minutes": 0,
             "absent_days": 0, "excused_days": 0, "worked_minutes": 0}

        day = first
        while day <= last:
            is_working, start, end = schedule_for(u.id, day)
            att = att_by_user_day.get((u.id, day))

            flags: list[str] = []
            if att is not None:
                status = att.status
                # Qo'lda tuzatilgan kun: apply_manual_attendance GPS izini
                # tozalaydi — check_in bor-u masofa yo'q bo'lsa, qo'lda kiritilgan.
                if att.note and AUTO_CLOSED_MARK in att.note:
                    flags.append("auto_closed")
                elif att.check_in_time is not None and att.check_in_distance_m is None:
                    flags.append("manual")
                if att.check_in_time is not None and att.check_out_time is None and day < today:
                    flags.append("no_checkout")
                cell = {
                    "date": day.isoformat(),
                    "status": status,
                    "late_minutes": att.late_minutes,
                    "check_in": _hm_local(att.check_in_time),
                    "check_out": _hm_local(att.check_out_time),
                    "worked_minutes": att.worked_minutes,
                    "schedule_start": start,
                    "schedule_end": end,
                    "note": att.note,
                    "flags": flags,
                }
            else:
                if day > today:
                    status = "weekend" if not is_working else "future"
                elif not is_working:
                    status = AttendanceStatus.weekend.value
                elif (u.id, day) in excused_days:
                    status = AttendanceStatus.excused.value
                elif day == today:
                    status = "pending"
                else:
                    status = AttendanceStatus.absent.value  # virtual — yozuvsiz
                cell = {
                    "date": day.isoformat(),
                    "status": status,
                    "late_minutes": 0,
                    "check_in": None,
                    "check_out": None,
                    "worked_minutes": 0,
                    "schedule_start": start,
                    "schedule_end": end,
                    "note": None,
                    "flags": flags,
                }

            s = cell["status"]
            if cell["check_in"] is not None:
                t["present_days"] += 1
            if s == AttendanceStatus.late.value:
                t["late_count"] += 1
                t["late_minutes"] += cell["late_minutes"]
            elif s == AttendanceStatus.absent.value:
                t["absent_days"] += 1
            elif s == AttendanceStatus.excused.value:
                t["excused_days"] += 1
            t["worked_minutes"] += cell["worked_minutes"]

            cells.append(cell)
            day += timedelta(days=1)

        out[u.id] = {
            "cells": cells,
            "totals": {**t, "worked_hours": round(t["worked_minutes"] / 60, 1)},
        }
    return out
