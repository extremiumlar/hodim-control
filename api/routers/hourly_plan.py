"""Soatma-soat reja: xodimning kunlik normasini ish jadvalidagi soatlarga bo'lib,
har soatda nima qilish kerakligini (reja) va haqiqiy natija (CRM) bilan solishtirib
ko'rsatadi. Xodim botda ochib ko'radi; scheduler har soatda avtomatik eslatadi."""
from datetime import date, datetime

from fastapi import APIRouter, Depends, status, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import settings
from api.deps import get_db, verify_bot_secret
from api.schemas import HourlyMetricStatus, HourlyPlanOut
from api.telegram_notify import send_message
from api.timeutil import TASHKENT_TZ, today_local
from db.models import Role, User, WorkScheduleOverride, WorkScheduleWeekly

router = APIRouter(prefix="/hourly-plan", tags=["hourly-plan"])

WEEKDAYS_UZ = ["Dush", "Sesh", "Chor", "Pay", "Jum", "Shan", "Yak"]
DEFAULT_START = "09:00"
DEFAULT_END = "18:00"


def _to_min(hm: str) -> int:
    h, m = hm.split(":")
    return int(h) * 60 + int(m)


async def _effective_today(db: AsyncSession, user: User, day: date) -> tuple[bool, str, str]:
    """Bugungi amaldagi ish oynasi: (is_working, start, end). Override > haftalik >
    default. Vaqt belgilanmagan ish kuni uchun default 09:00–18:00."""
    ov = await db.scalar(
        select(WorkScheduleOverride).where(
            WorkScheduleOverride.user_id == user.id, WorkScheduleOverride.date == day
        )
    )
    if ov is not None:
        if not ov.is_working:
            return False, "", ""
        return True, ov.start_time or DEFAULT_START, ov.end_time or DEFAULT_END

    w = await db.scalar(
        select(WorkScheduleWeekly).where(
            WorkScheduleWeekly.user_id == user.id, WorkScheduleWeekly.weekday == day.weekday()
        )
    )
    if w is not None:
        if not w.is_working:
            return False, "", ""
        return True, w.start_time or DEFAULT_START, w.end_time or DEFAULT_END

    # Jadval belgilanmagan — default ish oynasi (soatlik reja baribir ishlashi uchun)
    return True, DEFAULT_START, DEFAULT_END


async def build_plan(db: AsyncSession, user: User, now: datetime) -> HourlyPlanOut:
    from api.routers.stats import today_metric_rows  # circular importdan qochish

    day = now.date()
    is_working, start, end = await _effective_today(db, user, day)
    header = f"📋 <b>Bugungi rejam — {day:%d.%m} ({WEEKDAYS_UZ[day.weekday()]})</b>"

    if not is_working:
        return HourlyPlanOut(
            date=day, is_working=False,
            text=f"{header}\n\n🌙 Bugun dam olish kuni (ish jadvali bo'yicha).",
        )

    start_min, end_min = _to_min(start), _to_min(end)
    total = max(end_min - start_min, 1)
    total_hours = total / 60
    now_min = now.hour * 60 + now.minute
    elapsed = min(max(now_min - start_min, 0), total)
    frac = elapsed / total

    metric_rows = await today_metric_rows(db, user)
    statuses: list[HourlyMetricStatus] = []
    for r in metric_rows:
        if not r.norm or r.norm <= 0:
            continue
        per_hour = r.norm / total_hours
        statuses.append(
            HourlyMetricStatus(
                key=r.key, label=r.label, norm=r.norm,
                per_hour=round(per_hour, 1),
                this_hour_target=max(round(per_hour), 1),
                cumulative_target=round(r.norm * frac),
                actual=r.value,
                delta=r.value - round(r.norm * frac),
            )
        )

    now_hm = f"{now.hour:02d}:{now.minute:02d}"
    lines = [header, f"🕘 Ish vaqti: {start}–{end} | Hozir: {now_hm}", ""]

    if not statuses:
        lines.append("Sizga hali kunlik norma belgilanmagan — rahbaringizga murojaat qiling.")
    else:
        before_start = now_min < start_min
        after_end = now_min >= end_min
        for s in statuses:
            if s.delta >= 0:
                mark = f"✅ +{s.delta}" if s.delta else "✅ rejada"
            else:
                mark = f"⚠️ {s.delta}"
            lines.append(f"<b>{s.label}</b> — kunlik reja: {s.norm}")
            lines.append(f"  Shu paytgacha: kerak {s.cumulative_target} / bajarildi {s.actual}  {mark}")
            if before_start:
                lines.append(f"  Ish {start} da boshlanadi (soatiga ~{s.this_hour_target} ta)")
            elif after_end:
                lines.append("  Ish vaqti tugadi")
            else:
                lines.append(f"  ⏱ Bu soatda: ~{s.this_hour_target} ta")
            lines.append("")
        # Soatlik reja jadvali (birinchi ko'rsatkich bo'yicha)
        first = statuses[0]
        blocks = []
        b = start_min
        while b < end_min:
            b2 = min(b + 60, end_min)
            blocks.append(f"{b // 60:02d}:{b % 60:02d}–{b2 // 60:02d}:{b2 % 60:02d}")
            b += 60
        lines.append(f"📊 Soatlik reja ({first.label.lower()}): har blokda ~{first.this_hour_target} ta")
        lines.append(" · ".join(blocks))

    return HourlyPlanOut(
        date=day, is_working=True, start_time=start, end_time=end, now=now_hm,
        metrics=statuses, text="\n".join(lines).strip(),
    )


@router.get("/{telegram_id}/me", response_model=HourlyPlanOut, dependencies=[Depends(verify_bot_secret)])
async def my_hourly_plan(telegram_id: int, db: AsyncSession = Depends(get_db)) -> HourlyPlanOut:
    """Xodim botda ochganda: hozirgi holatga qarab bugungi soatma-soat reja + progress."""
    user = await db.scalar(select(User).where(User.telegram_id == telegram_id))
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Foydalanuvchi topilmadi")
    return await build_plan(db, user, datetime.now(TASHKENT_TZ))


@router.post("/send", dependencies=[Depends(verify_bot_secret)])
async def send_hourly_plan(db: AsyncSession = Depends(get_db)) -> dict:
    """Scheduler har soat boshida chaqiradi: ayni damда ish vaqtida bo'lgan va normasi
    bor xodimlarga shu soat rejasini + progressni yuboradi. Ish vaqtidan tashqarida
    (yoki dam olish kunida) hech kimga yuborilmaydi. Xavfsizlik uchun default o'chiq
    (settings.hourly_plan_enabled) — haqiqiy xodimlarga xabar ketgani sabab."""
    if not settings.hourly_plan_enabled:
        return {"sent": 0, "disabled": True}
    now = datetime.now(TASHKENT_TZ)
    users = list(
        await db.scalars(
            select(User).where(
                User.role == Role.employee.value,
                User.is_active == True,  # noqa: E712
                User.telegram_id.isnot(None),
            )
        )
    )
    sent = 0
    for user in users:
        plan = await build_plan(db, user, now)
        if not plan.is_working or not plan.metrics:
            continue
        # Faqat ish oynasi ichida (rejada boshlanmagan/tugagan bo'lsa yubormaymiz)
        if plan.start_time and plan.end_time:
            now_min = now.hour * 60 + now.minute
            if now_min < _to_min(plan.start_time) or now_min >= _to_min(plan.end_time):
                continue
        result = await send_message(user.telegram_id, plan.text)
        if result is not None:
            sent += 1
    return {"sent": sent, "at": f"{now.hour:02d}:{now.minute:02d}", "date": today_local().isoformat()}
