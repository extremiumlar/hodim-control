"""Operator AI — avto-reja dvigateli (2-bosqich).

Uch bosqichli oqim:
  1. `snapshot_hourly_actual` / `backfill_hourly_actual` — CRM call-history'dan
     operator × sana × soat kompozit sifatni `hourly_actual`ga yozadi.
  2. `compute_profiles` — oxirgi ~30 kun `hourly_actual`dan har operator/soat uchun
     "odatiy temp" (`operator_profile`, median asosida) hisoblaydi.
  3. `build_daily_targets` — profil (o'z imkoniyati) + jamoa benchmarki + kichik
     stretch'dan ish jadvaliga moslangan `hourly_target` tuzadi.

Bularning hammasi kod (aniq, arzon) — Claude qatlami (3-bosqich) faqat natijani
odam tiliga o'giradi. Barcha yozuvlar grain bo'yicha idempotent (upsert)."""
import logging
from datetime import date, timedelta
from statistics import median

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from crm import get_crm_adapter
from db.models import HourlyActual, HourlyTarget, OperatorProfile, Role, User
from db.upsert import upsert

logger = logging.getLogger(__name__)

# Reja tuzish parametrlari (dizayn: "o'z imkoniyati + jamoa benchmarki + kichik stretch")
PROFILE_LOOKBACK_DAYS = 30
PERSONAL_WEIGHT = 0.7  # shaxsiy imkoniyatga urg'u
TEAM_WEIGHT = 0.3  # jamoa benchmarki bilan ko'tarish
STRETCH = 0.10  # kichik o'sish maqsadi (10%)
LUNCH_HOUR = 13  # 13:00–14:00 — reja tuzilmaydi ([[hourly-plan-feature]] bilan bir xil)

_ACTUAL_METRICS = ("calls", "calls_in", "calls_out", "answered", "talk_sec", "short_calls")


async def _emp_to_user_id(db: AsyncSession) -> dict[str, int]:
    """`employeeNum` (email = `crm_external_id`) → tizim `User.id`. Bog'lanmagan
    qo'ng'iroqlar (test/boshqa akkauntlar) e'tiborga olinmaydi — reja faqat
    tizimdagi operatorlar uchun."""
    users = list(await db.scalars(select(User).where(User.crm_external_id.isnot(None), User.is_active == True)))  # noqa: E712
    return {u.crm_external_id: u.id for u in users if u.crm_external_id}


async def _upsert_hourly_actual(db: AsyncSession, rows: list[dict]) -> None:
    if not rows:
        return
    stmt = upsert(HourlyActual).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["user_id", "date", "hour"],
        set_={m: getattr(stmt.excluded, m) for m in _ACTUAL_METRICS},
    )
    await db.execute(stmt)


def _bucket_row(user_id: int, day: date, hour: int, bucket: dict) -> dict:
    return {
        "user_id": user_id,
        "date": day,
        "hour": hour,
        **{m: int(bucket.get(m, 0)) for m in _ACTUAL_METRICS},
    }


async def snapshot_hourly_actual(db: AsyncSession, day: date) -> int:
    """Bitta kun (odatda bugun) uchun soatlik actual'ni CRM'dan o'qib yozadi.
    CRM xatosida jadval o'zgarmaydi (-1). Yozilgan (user×soat) qatorlar sonini qaytaradi."""
    adapter = get_crm_adapter_or_none()
    if adapter is None:
        return -1
    data = await adapter.get_hourly_call_quality(day)
    if data is None:
        return -1

    emp_map = await _emp_to_user_id(db)
    rows: list[dict] = []
    for emp, payload in data.items():
        user_id = emp_map.get(emp)
        if user_id is None:
            continue
        for hour, bucket in payload.get("hours", {}).items():
            rows.append(_bucket_row(user_id, day, int(hour), bucket))
    await _upsert_hourly_actual(db, rows)
    await db.commit()
    return len(rows)


async def backfill_hourly_actual(db: AsyncSession, day_from: date, day_to: date) -> int:
    """Bootstrap: [day_from, day_to] oralig'ini bitta CRM skanerda o'qib yozadi
    (profil hisoblash uchun tarixiy baza). Uzoq ish. Yozilgan qatorlar sonini qaytaradi."""
    adapter = get_crm_adapter_or_none()
    if adapter is None:
        return -1
    data = await adapter.get_hourly_call_quality_range(day_from, day_to)
    if data is None:
        return -1

    emp_map = await _emp_to_user_id(db)
    rows: list[dict] = []
    for emp, per_day in data.items():
        user_id = emp_map.get(emp)
        if user_id is None:
            continue
        for day_iso, hours in per_day.items():
            d = date.fromisoformat(day_iso)
            for hour, bucket in hours.items():
                rows.append(_bucket_row(user_id, d, int(hour), bucket))
    await _upsert_hourly_actual(db, rows)
    await db.commit()
    return len(rows)


def get_crm_adapter_or_none():
    from api.config import settings

    return get_crm_adapter(settings.crm_type)


async def compute_profiles(db: AsyncSession, today: date, lookback_days: int = PROFILE_LOOKBACK_DAYS) -> int:
    """Oxirgi `lookback_days` kun `hourly_actual`dan har operator/soat uchun odatiy
    tempni (median) hisoblab `operator_profile`ni yangilaydi. Faqat operator (`employee`)
    rollari. Yangilangan profil qatorlari sonini qaytaradi."""
    start = today - timedelta(days=lookback_days)
    employee_ids = set(
        await db.scalars(
            select(User.id).where(User.role == Role.employee.value, User.is_active == True)  # noqa: E712
        )
    )
    if not employee_ids:
        return 0

    actuals = list(
        await db.scalars(
            select(HourlyActual).where(HourlyActual.date >= start, HourlyActual.date < today)
        )
    )
    # (user_id, hour) -> per-day qiymatlar ro'yxati
    grouped: dict[tuple[int, int], dict[str, list[int]]] = {}
    for a in actuals:
        if a.user_id not in employee_ids:
            continue
        g = grouped.setdefault((a.user_id, a.hour), {"calls": [], "answered": [], "talk_sec": []})
        g["calls"].append(a.calls)
        g["answered"].append(a.answered)
        g["talk_sec"].append(a.talk_sec)

    count = 0
    for (user_id, hour), vals in grouped.items():
        sample_days = len(vals["calls"])
        row = {
            "user_id": user_id,
            "hour": hour,
            "baseline_calls": int(round(median(vals["calls"]))) if vals["calls"] else 0,
            "baseline_answered": int(round(median(vals["answered"]))) if vals["answered"] else 0,
            "baseline_talk_sec": int(round(median(vals["talk_sec"]))) if vals["talk_sec"] else 0,
            "sample_days": sample_days,
        }
        stmt = upsert(OperatorProfile).values(row)
        stmt = stmt.on_conflict_do_update(
            index_elements=["user_id", "hour"],
            set_={
                "baseline_calls": stmt.excluded.baseline_calls,
                "baseline_answered": stmt.excluded.baseline_answered,
                "baseline_talk_sec": stmt.excluded.baseline_talk_sec,
                "sample_days": stmt.excluded.sample_days,
            },
        )
        await db.execute(stmt)
        count += 1
    await db.commit()
    return count


def _blend_target(personal: int, team: float) -> int:
    """o'z imkoniyati + jamoa benchmarki + kichik stretch → yaxlit maqsad."""
    base = PERSONAL_WEIGHT * personal + TEAM_WEIGHT * team
    return int(round(base * (1 + STRETCH)))


async def build_daily_targets(db: AsyncSession, day: date) -> int:
    """`operator_profile` + jamoa benchmarki + stretch'dan `day` uchun soatlik reja
    tuzadi, ish jadvali oynasiga moslaydi (dam kuni → reja yo'q, tushlik soati
    o'tkaziladi). Yozilgan (user×soat) target qatorlari sonini qaytaradi."""
    from api.routers.hourly_plan import _effective_today, _to_min  # circular importdan qochish

    profiles = list(await db.scalars(select(OperatorProfile)))
    if not profiles:
        return 0

    # user_id -> {hour: profile}
    by_user: dict[int, dict[int, OperatorProfile]] = {}
    # hour -> operatorlarning baseline_calls ro'yxati (jamoa benchmarki uchun)
    team_hour_calls: dict[int, list[int]] = {}
    for p in profiles:
        by_user.setdefault(p.user_id, {})[p.hour] = p
        if p.baseline_calls > 0:
            team_hour_calls.setdefault(p.hour, []).append(p.baseline_calls)
    team_median_calls = {h: median(v) for h, v in team_hour_calls.items()}

    users = {
        u.id: u
        for u in await db.scalars(
            select(User).where(User.id.in_(by_user.keys()), User.is_active == True)  # noqa: E712
        )
    }

    count = 0
    for user_id, hours in by_user.items():
        user = users.get(user_id)
        if user is None:
            continue
        is_working, start, end = await _effective_today(db, user, day)
        if not is_working:
            continue
        start_hour = _to_min(start) // 60
        end_hour = (_to_min(end) + 59) // 60  # oxirgi qisman soatni ham qamrab olamiz
        for hour in range(start_hour, end_hour):
            if hour == LUNCH_HOUR:
                continue  # tushlik — reja yo'q
            prof = hours.get(hour)
            personal_calls = prof.baseline_calls if prof else 0
            personal_ans = prof.baseline_answered if prof else 0
            personal_talk = prof.baseline_talk_sec if prof else 0
            team_calls = team_median_calls.get(hour, 0)

            row = {
                "user_id": user_id,
                "date": day,
                "hour": hour,
                "target_calls": _blend_target(personal_calls, team_calls),
                # sifat maqsadi ko'proq shaxsiy (jamoa benchmarkisiz, faqat stretch)
                "target_answered": int(round(personal_ans * (1 + STRETCH))),
                "target_talk_sec": personal_talk,
            }
            stmt = upsert(HourlyTarget).values(row)
            stmt = stmt.on_conflict_do_update(
                index_elements=["user_id", "date", "hour"],
                set_={
                    "target_calls": stmt.excluded.target_calls,
                    "target_answered": stmt.excluded.target_answered,
                    "target_talk_sec": stmt.excluded.target_talk_sec,
                },
            )
            await db.execute(stmt)
            count += 1
    await db.commit()
    return count
