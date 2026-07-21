"""Kunlik davomat (kelib-ketish) digesti — guruhga avtomatik yuboriladi.

Ikki xil digest:
  • ertalabki (default 09:30) — kim keldi, kim kechikdi, kim hali kelmadi;
  • kechki (default 22:00) — kun yakuni: ish vaqti, kechikishlar, chiqmaganlar,
    umuman kelmaganlar.

Ma'lumot manbai: `attendance` jadvali + xodimning o'sha kungi ish jadvali
(WorkScheduleOverride > WorkScheduleWeekly > default) + tasdiqlangan sababli
kunlar. Faqat `role=employee` — rahbarlar davomat ro'yxatida ko'rsatilmaydi
(late-stats/employee-summary bilan bir xil qoida).

Dam olish kuni (hech kim ishlamaydi) — digest yuborilmaydi (guruhda shovqin
bo'lmasligi uchun)."""
import html
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.routers.hourly_plan import _effective_today
from api.services.attendance import ATTENDANCE_TRACKED_ROLES
from api.services.daily_digest import digest_group_targets
from api.telegram_notify import send_message
from api.timeutil import TASHKENT_TZ, today_local
from db.models import (
    Attendance,
    AttendanceDigestConfig,
    ExcusedDay,
    ExcusedStatus,
    User,
)

WEEKDAYS_UZ = ["Dushanba", "Seshanba", "Chorshanba", "Payshanba", "Juma", "Shanba", "Yakshanba"]
MONTHS_UZ = [
    "yanvar", "fevral", "mart", "aprel", "may", "iyun",
    "iyul", "avgust", "sentabr", "oktabr", "noyabr", "dekabr",
]


def _fmt_local(dt: datetime | None) -> str:
    """Bazadagi naive-UTC vaqtni Toshkent soatiga o'giradi: '08:52'."""
    if dt is None:
        return "—"
    return dt.replace(tzinfo=timezone.utc).astimezone(TASHKENT_TZ).strftime("%H:%M")


def _fmt_date(d) -> str:
    return f"{d.day}-{MONTHS_UZ[d.month - 1]}, {WEEKDAYS_UZ[d.weekday()]}"


def _name(u: User) -> str:
    return html.escape(u.full_name)


def _minute_of_day(dt: datetime) -> int:
    """naive-UTC vaqtdan Toshkent kunidagi daqiqa (0-1439)."""
    local = dt.replace(tzinfo=timezone.utc).astimezone(TASHKENT_TZ)
    return local.hour * 60 + local.minute


def _hm_to_min(hm: str) -> int:
    h, m = hm.split(":")
    return int(h) * 60 + int(m)


async def collect_day(db: AsyncSession, day=None) -> dict:
    """Kunning davomat manzarasi — ikkala digest uchun YAGONA yig'uvchi.

    Qaytaradi: {day, expected, present, late, early_in, absent, excused,
    no_checkout, early_out, late_out}. Har bir "vaqt" ro'yxati (user, att, daqiqa)
    uchligi: `early_in` — jadvaldan necha daqiqa erta kelgan; `early_out` — erta
    ketgan; `late_out` — ish oynasi tugagach necha daqiqa ortiqcha qolgan.
    Kechikish (`late`) Attendance.late_minutes'dan (grace bilan hisoblangan),
    qolganlari shu yerda ish jadvali oynasidan hisoblanadi."""
    day = day or today_local()

    employees = list(
        await db.scalars(
            select(User).where(
                User.is_active.is_(True), User.role.in_(ATTENDANCE_TRACKED_ROLES)
            )
        )
    )
    att_rows = {
        a.user_id: a
        for a in await db.scalars(select(Attendance).where(Attendance.date == day))
    }
    excused_ids = {
        e.user_id
        for e in await db.scalars(
            select(ExcusedDay).where(
                ExcusedDay.date == day, ExcusedDay.status == ExcusedStatus.approved.value
            )
        )
    }

    expected: list[User] = []  # bugun ishlashi kerak bo'lganlar
    present: list[tuple[User, Attendance]] = []
    late: list[tuple[User, Attendance]] = []
    early_in: list[tuple[User, Attendance, int]] = []
    absent: list[User] = []
    excused: list[User] = []
    no_checkout: list[tuple[User, Attendance]] = []
    early_out: list[tuple[User, Attendance, int]] = []
    late_out: list[tuple[User, Attendance, int]] = []

    for u in employees:
        is_working, start, end = await _effective_today(db, u, day)
        if not is_working:
            continue  # dam olish kuni — ro'yxatga kirmaydi
        expected.append(u)

        att = att_rows.get(u.id)
        if att is not None and att.check_in_time is not None:
            present.append((u, att))
            if att.late_minutes > 0:
                late.append((u, att))
            elif start:
                # Kechikmagan bo'lsa — jadvaldan qancha erta kelgani
                early = _hm_to_min(start) - _minute_of_day(att.check_in_time)
                if early > 0:
                    early_in.append((u, att, early))

            if att.check_out_time is None:
                no_checkout.append((u, att))
            elif end:
                diff = _minute_of_day(att.check_out_time) - _hm_to_min(end)
                if diff > 0:
                    late_out.append((u, att, diff))
                elif att.early_leave_minutes > 0:
                    early_out.append((u, att, att.early_leave_minutes))
        elif u.id in excused_ids:
            excused.append(u)
        else:
            absent.append(u)

    late.sort(key=lambda p: p[1].late_minutes, reverse=True)
    early_in.sort(key=lambda p: p[2], reverse=True)
    early_out.sort(key=lambda p: p[2], reverse=True)
    late_out.sort(key=lambda p: p[2], reverse=True)
    present.sort(key=lambda p: p[1].check_in_time or datetime.max)

    return {
        "day": day,
        "expected": expected,
        "present": present,
        "late": late,
        "early_in": early_in,
        "absent": absent,
        "excused": excused,
        "no_checkout": no_checkout,
        "early_out": early_out,
        "late_out": late_out,
    }


def build_morning_text(data: dict) -> str:
    """Ertalabki digest — hozirgi holat (kim keldi/kechikdi/hali yo'q)."""
    now_hm = datetime.now(TASHKENT_TZ).strftime("%H:%M")
    present, late = data["present"], data["late"]
    late_ids = {u.id for u, _ in late}
    on_time = [(u, a) for u, a in present if u.id not in late_ids]

    lines = [
        f"🌅 <b>Ertalabki davomat</b> — {_fmt_date(data['day'])} ({now_hm})",
        "",
        f"👥 Bugun ishlashi kerak: <b>{len(data['expected'])}</b> · "
        f"keldi: <b>{len(present)}</b> · kelmadi: <b>{len(data['absent'])}</b>",
    ]

    early_in = data["early_in"]
    early_ids = {u.id for u, _, _ in early_in}

    if early_in:
        lines += ["", f"🌟 <b>Erta keldi ({len(early_in)}):</b>"]
        lines += [
            f"  • {_name(u)} — {_fmt_local(a.check_in_time)} ({mins} daq erta)"
            for u, a, mins in early_in
        ]

    exact = [(u, a) for u, a in on_time if u.id not in early_ids]
    if exact:
        lines += ["", f"✅ <b>O'z vaqtida ({len(exact)}):</b>"]
        lines += [f"  • {_name(u)} — {_fmt_local(a.check_in_time)}" for u, a in exact]

    if late:
        total = sum(a.late_minutes for _, a in late)
        lines += ["", f"⏰ <b>Kechikdi ({len(late)}) — jami {total} daq:</b>"]
        lines += [
            f"  • {_name(u)} — {_fmt_local(a.check_in_time)} (+{a.late_minutes} daq)"
            for u, a in late
        ]

    if data["absent"]:
        lines += ["", f"❌ <b>Hali kelmadi ({len(data['absent'])}):</b>"]
        lines += [f"  • {_name(u)}" for u in data["absent"]]

    if data["excused"]:
        lines += ["", f"🏖 <b>Sababli ({len(data['excused'])}):</b> " +
                  ", ".join(_name(u) for u in data["excused"])]

    return "\n".join(lines)


def build_evening_text(data: dict) -> str:
    """Kechki digest — kun yakuni (ish vaqti, kechikish, chiqmaganlar)."""
    present, late = data["present"], data["late"]
    lines = [
        f"🌙 <b>Kunlik davomat yakuni</b> — {_fmt_date(data['day'])}",
        "",
        f"👥 Ishlashi kerak edi: <b>{len(data['expected'])}</b> · "
        f"keldi: <b>{len(present)}</b> · kelmadi: <b>{len(data['absent'])}</b>",
    ]

    if late:
        total = sum(a.late_minutes for _, a in late)
        lines += ["", f"⏰ <b>Kech kelganlar ({len(late)}) — jami {total} daq:</b>"]
        lines += [f"  • {_name(u)} +{a.late_minutes} daq ({_fmt_local(a.check_in_time)})"
                  for u, a in late]

    if data["early_in"]:
        lines += ["", f"🌟 <b>Erta kelganlar ({len(data['early_in'])}):</b>"]
        lines += [f"  • {_name(u)} {mins} daq erta ({_fmt_local(a.check_in_time)})"
                  for u, a, mins in data["early_in"]]

    if data["early_out"]:
        lines += ["", f"🏃 <b>Erta ketganlar ({len(data['early_out'])}):</b>"]
        lines += [f"  • {_name(u)} {mins} daq erta ({_fmt_local(a.check_out_time)})"
                  for u, a, mins in data["early_out"]]

    if data["late_out"]:
        lines += ["", f"🌜 <b>Kech ketganlar ({len(data['late_out'])}):</b>"]
        lines += [f"  • {_name(u)} +{mins} daq ortiqcha ({_fmt_local(a.check_out_time)})"
                  for u, a, mins in data["late_out"]]

    if present:
        lines += ["", "🕐 <b>Ish vaqti:</b>"]
        for u, a in present:
            worked = f"{round(a.worked_minutes / 60, 1)} soat" if a.worked_minutes else "—"
            out = _fmt_local(a.check_out_time) if a.check_out_time else "chiqmadi"
            lines.append(f"  • {_name(u)} — {_fmt_local(a.check_in_time)} → {out} ({worked})")

    if data["no_checkout"]:
        lines += ["", f"🚪 <b>«Ketdim» bosmaganlar ({len(data['no_checkout'])}):</b> " +
                  ", ".join(_name(u) for u, _ in data["no_checkout"])]

    if data["absent"]:
        lines += ["", f"❌ <b>Kelmaganlar ({len(data['absent'])}):</b> " +
                  ", ".join(_name(u) for u in data["absent"])]

    if data["excused"]:
        lines += ["", f"🏖 <b>Sababli ({len(data['excused'])}):</b> " +
                  ", ".join(_name(u) for u in data["excused"])]

    return "\n".join(lines)


async def get_digest_config(db: AsyncSession) -> AttendanceDigestConfig:
    """Sozlama qatorini (id=1) oladi, bo'lmasa defaultlar bilan yaratadi."""
    cfg = await db.get(AttendanceDigestConfig, 1)
    if cfg is None:
        cfg = AttendanceDigestConfig(id=1)
        db.add(cfg)
        await db.commit()
        await db.refresh(cfg)
    return cfg


async def digest_tick(db: AsyncSession) -> dict:
    """Cron har daqiqa chaqiradi. Sozlangan vaqt YETGAN yoki O'TGAN va bugun hali
    yuborilmagan bo'lsa — tegishli digestni yuboradi. `>=` semantikasi ataylab:
    cron aynan o'sha daqiqani o'tkazib yuborsa ham (restart, kechikish) keyingi
    tick'da baribir yuboriladi; `*_last_posted` bir kunda ikki marta yuborilishdan
    saqlaydi (lid digesti group-tick bilan bir xil naqsh)."""
    cfg = await get_digest_config(db)
    now = datetime.now(TASHKENT_TZ)
    today = now.date()
    fired: list[dict] = []

    for kind, enabled, hour, minute, last in (
        ("morning", cfg.morning_enabled, cfg.morning_hour, cfg.morning_minute, cfg.morning_last_posted),
        ("evening", cfg.evening_enabled, cfg.evening_hour, cfg.evening_minute, cfg.evening_last_posted),
    ):
        if not enabled or last == today:
            continue
        if (now.hour, now.minute) < (hour, minute):
            continue
        result = await send_attendance_digest(db, kind=kind)
        # Dam olish kuni (yuborilmadi) bo'lsa ham bugungi kunni belgilaymiz —
        # aks holda har daqiqada qayta urinib, keraksiz ish bajarilaverardi.
        if kind == "morning":
            cfg.morning_last_posted = today
        else:
            cfg.evening_last_posted = today
        await db.commit()
        fired.append({"kind": kind, **result})

    if fired:
        return {"fired": True, "results": fired}
    return {
        "fired": False,
        "morning": f"{cfg.morning_hour:02d}:{cfg.morning_minute:02d}",
        "evening": f"{cfg.evening_hour:02d}:{cfg.evening_minute:02d}",
    }


async def send_attendance_digest(
    db: AsyncSession, kind: str, chat_id: int | None = None, dry_run: bool = False
) -> dict:
    """Davomat digestini guruh(lar)ga yuboradi. kind: 'morning' | 'evening'.
    Bugun hech kim ishlamasa (dam olish kuni) — yuborilmaydi."""
    if kind not in ("morning", "evening"):
        return {"sent": False, "reason": f"noma'lum digest turi: {kind}"}

    data = await collect_day(db)
    if not data["expected"]:
        return {"sent": False, "reason": "bugun hech kim ishlamaydi (dam olish kuni)"}

    text = build_morning_text(data) if kind == "morning" else build_evening_text(data)
    if dry_run:
        return {"sent": False, "dry_run": True, "text": text}

    targets = digest_group_targets(chat_id)
    if not targets:
        return {"sent": False, "reason": "guruh sozlanmagan (TELEGRAM_GROUP_CHAT_ID)"}

    delivered = 0
    for cid in targets:
        if await send_message(cid, text):
            delivered += 1
    return {"sent": delivered > 0, "kind": kind, "chats": delivered, "text": text}
