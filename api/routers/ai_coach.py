"""Operator AI Claude qatlamini sinash/ishlatish endpointlari (3-bosqich).

Bu yerda faqat AGREGATLAR quriladi (PII yo'q) va `ai_coach` servisiga beriladi.
Servis AI o'chiq bo'lsa deterministik fallback matn qaytaradi, shuning uchun bu
endpointlar AI yoqilmagan holatda ham ishlaydi (matn hosil qiladi, lekin hech
kimga yubormaydi — yuborish 4/6-bosqichda scheduler/bot orqali)."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_db, verify_bot_secret
from api.services import ai_coach
from api.timeutil import TASHKENT_TZ, today_local
from db.models import HourlyActual, HourlyTarget, Role, ShortfallReason, User

router = APIRouter(prefix="/ai-coach", tags=["ai-coach"], dependencies=[Depends(verify_bot_secret)])


async def _operator_day(db: AsyncSession, user_id: int, day) -> dict:
    """Bitta operatorning shu kundagi target/actual agregati (soatlik yig'indi)."""
    targets = list(
        await db.scalars(select(HourlyTarget).where(HourlyTarget.user_id == user_id, HourlyTarget.date == day))
    )
    actuals = list(
        await db.scalars(select(HourlyActual).where(HourlyActual.user_id == user_id, HourlyActual.date == day))
    )
    day_target = sum(t.target_calls for t in targets)
    done = sum(a.calls for a in actuals)
    answered = sum(a.answered for a in actuals)
    talk = sum(a.talk_sec for a in actuals)
    return {
        "targets": {t.hour: t.target_calls for t in targets},
        "day_target": day_target,
        "day_done": done,
        "answered": answered,
        "avg_talk_sec": round(talk / answered) if answered else 0,
        "short_calls": sum(a.short_calls for a in actuals),
    }


@router.post("/nudge/{telegram_id}")
async def nudge(telegram_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    """Bitta operator uchun hozirgi holatga (reja vs haqiqiy) qarab yo'naltiruvchi matn."""
    user = await db.scalar(select(User).where(User.telegram_id == telegram_id))
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Foydalanuvchi topilmadi")
    now = datetime.now(TASHKENT_TZ)
    day = now.date()
    agg = await _operator_day(db, user.id, day)

    cur_hour, frac = now.hour, now.minute / 60
    planned_so_far = 0
    for hour, tc in agg["targets"].items():
        if hour < cur_hour:
            planned_so_far += tc
        elif hour == cur_hour:
            planned_so_far += round(tc * frac)

    payload = {
        "name": user.full_name.split()[0] if user.full_name else "",
        "hour": cur_hour,
        "planned_so_far": planned_so_far,
        "done_so_far": agg["day_done"],
        "avg_talk_sec": agg["avg_talk_sec"],
        "short_calls": agg["short_calls"],
        "day_target": agg["day_target"],
        "day_done": agg["day_done"],
    }
    return await ai_coach.coach_nudge(db, user.id, payload)


@router.post("/group-summary")
async def group_summary(db: AsyncSession = Depends(get_db)) -> dict:
    """Bugungi jamoa uchun kun yakuni xulosasi (barcha sotuv operatorlari agregati)."""
    day = today_local()
    employees = list(
        await db.scalars(
            select(User).where(
                User.role == Role.employee.value, User.is_active == True, User.crm_external_id.isnot(None)  # noqa: E712
            )
        )
    )
    operators = []
    total_target = total_done = 0
    for u in employees:
        agg = await _operator_day(db, u.id, day)
        if agg["day_target"] == 0 and agg["day_done"] == 0:
            continue  # bugun faoliyatsiz — tashlaymiz
        total_target += agg["day_target"]
        total_done += agg["day_done"]
        operators.append({
            "name": u.full_name.split()[0] if u.full_name else "",
            "done": agg["day_done"],
            "target": agg["day_target"],
            "avg_talk": agg["avg_talk_sec"],
            "top": False,
        })
    if operators:
        best = max(operators, key=lambda o: o["done"])
        best["top"] = True
    # Bugun operatorlardan yig'ilgan sabablar — jamlanib rahbarga tizimli ko'rinadi
    # ("3 operator 'baza tugadi' dedi"). Bir operator bir sababni bir necha soatda
    # bosgan bo'lsa ham bir marta sanaladi (operator kesimida noyob).
    reason_rows = list(
        await db.scalars(select(ShortfallReason).where(ShortfallReason.date == day))
    )
    by_reason: dict[str, set[int]] = {}
    for r in reason_rows:
        by_reason.setdefault(r.reason, set()).add(r.user_id)
    reasons = sorted(
        ({"reason": k, "count": len(v)} for k, v in by_reason.items()),
        key=lambda x: -x["count"],
    )

    payload = {
        "date": day.isoformat(),
        "team_completion_pct": round(total_done / total_target * 100) if total_target else 0,
        "operators": operators,
        "reasons": reasons,
    }
    return await ai_coach.daily_group_summary(db, payload)
