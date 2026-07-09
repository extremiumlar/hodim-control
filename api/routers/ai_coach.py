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
        "actuals": {a.hour: a.calls for a in actuals},
        "day_target": day_target,
        "day_done": done,
        "answered": answered,
        "avg_talk_sec": round(talk / answered) if answered else 0,
        "short_calls": sum(a.short_calls for a in actuals),
    }


# Pasayish epizodi mezonlari: kumulyativ farq kamida shuncha qo'ng'iroq VA haqiqiy
# rejaning shu ulushidan past bo'lsa — soat "orqada" sanaladi (kichik raqamlardagi
# shovqin epizod bo'lib ketmasligi uchun ikkala shart ham kerak).
_DIP_MIN_GAP = 3
_DIP_RATIO = 0.75


def _dip_episodes(targets: dict[int, int], actuals: dict[int, int], upto_hour: int) -> list[dict]:
    """Kun ichidagi pasayish epizodlarini KOD aniqlaydi (AI emas — AI faqat tayyor
    faktni so'zlaydi). Epizod: ketma-ket soatlarda kumulyativ haqiqiy kumulyativ
    rejadan sezilarli orqada. `recovered` — keyingi soatlarda farq yopilgan
    (operator o'zini o'nglagan). `upto_hour` — hali kelmagan soatlar "pasayish"
    bo'lib ko'rinmasligi uchun chegara."""
    hours = sorted(h for h, t in targets.items() if t > 0 and h <= upto_hour)
    cum_t = cum_a = 0
    episodes: list[dict] = []
    current: dict | None = None
    for h in hours:
        cum_t += targets[h]
        cum_a += actuals.get(h, 0)
        gap = cum_t - cum_a
        behind = gap >= _DIP_MIN_GAP and cum_a < cum_t * _DIP_RATIO
        if behind:
            if current is None:
                current = {"from_hour": h, "to_hour": h, "max_gap": gap, "recovered": False}
            else:
                current["to_hour"] = h
                current["max_gap"] = max(current["max_gap"], gap)
        elif current is not None:
            current["recovered"] = True
            episodes.append(current)
            current = None
    if current is not None:
        episodes.append(current)
    return episodes


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
    """Bugungi jamoa uchun kun yakuni xulosasi (barcha sotuv operatorlari agregati).
    Har operatorga kun ichidagi pasayish epizodlari ("soat 14:00–16:00 orqada, keyin
    to'g'irladi") KOD tomonidan hisoblanib payload'ga qo'shiladi — AI aniq soat va
    holat bilan gapiradi, taxmin qilmaydi."""
    day = today_local()
    now = datetime.now(TASHKENT_TZ)
    upto_hour = now.hour if now.date() == day else 23
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
        dips = [
            {
                "from": f"{e['from_hour']:02d}:00",
                "to": f"{e['to_hour'] + 1:02d}:00",
                "recovered": e["recovered"],
                "max_gap_calls": e["max_gap"],
            }
            for e in _dip_episodes(agg["targets"], agg["actuals"], upto_hour)
        ]
        operators.append({
            "name": u.full_name.split()[0] if u.full_name else "",
            "done": agg["day_done"],
            "target": agg["day_target"],
            "avg_talk": agg["avg_talk_sec"],
            "dips": dips,
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
        # reason NULL — sabab so'ralgan, lekin operator javob yozmagan (bu ham signal);
        # verified=False — yozgan sababi fakt tekshiruvida mos kelmagan (rahbar bilsin).
        if r.reason is None:
            label = "Sabab yozilmagan"
        elif r.verified is False:
            label = f"{r.reason} (tekshiruv: mos kelmadi)"
        else:
            label = r.reason
        by_reason.setdefault(label, set()).add(r.user_id)
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
