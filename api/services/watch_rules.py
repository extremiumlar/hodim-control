"""Operator AI — arzon kuzatuv qoidalari (4-bosqich). Bu KOD, AI emas:
"faqat-kerakda-gapir" tamoyilining birinchi darvozasi. Har soat holatni tekshiradi
va FAQAT quyidagi hollarda nudge qaroriga keladi:

  - ORQADA QOLISH: kumulyativ bajarilgan < reja×BEHIND_RATIO va farq kamida
    BEHIND_MIN_GAP (kichik raqamlarda shovqin qilmaslik uchun) → sabab so'raladi.
  - ANOMALIYA: bugun qisqa (aldash/sayoz) qo'ng'iroqlar ko'p → ogohlantirish.

Adolat filtrlari (nazorat qilib bo'lmaydigan narsa uchun ayblamaslik):
  - dam olish kuni / ish oynasidan tashqari / tushlik — tekshirilmaydi;
  - kunning birinchi GRACE daqiqasi — hali "orqada" deb bo'lmaydi;
  - bugun tasdiqlangan sababli kun (ExcusedDay approved) — tekshirilmaydi.

Shovqin nazorati: bitta operatorga kuniga ko'pi bilan MAX_NUDGES_PER_DAY nudge,
ikkitasining orasi kamida COOLDOWN_MINUTES (ai_message_log'dan tekshiriladi)."""
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.timeutil import local_range_utc_naive
from db.models import AiMessageLog, ExcusedDay, ExcusedStatus, HourlyActual, HourlyTarget, Role, User

logger = logging.getLogger(__name__)

BEHIND_RATIO = 0.7  # bajarilgan < reja×0.7 bo'lsa "orqada"
BEHIND_MIN_GAP = 3  # mutlaq farq kamida shuncha bo'lsin (2/3 uchun bezovta qilmaymiz)
GRACE_MINUTES = 60  # ish boshidagi birinchi soat — baholanmaydi
LUNCH_HOUR = 13
MAX_NUDGES_PER_DAY = 3
COOLDOWN_MINUTES = 120
ANOMALY_SHORT_CALLS = 5  # bugun kamida shuncha qisqa qo'ng'iroq bo'lsa...
ANOMALY_SHORT_RATIO = 0.4  # ...va ular javob berilganlarning shunchasidan ko'pi bo'lsa


@dataclass
class NudgeDecision:
    user: User
    kind: str  # behind | anomaly
    ask_reason: bool
    payload: dict  # ai_coach.coach_nudge uchun agregat (PII yo'q)


async def _nudges_today(db: AsyncSession, user_id: int, day) -> list[AiMessageLog]:
    start_utc, end_utc = local_range_utc_naive(day, day)
    return list(
        await db.scalars(
            select(AiMessageLog).where(
                AiMessageLog.user_id == user_id,
                AiMessageLog.kind == "nudge",
                AiMessageLog.created_at >= start_utc,
                AiMessageLog.created_at < end_utc,
            ).order_by(AiMessageLog.created_at.desc())
        )
    )


async def _is_excused(db: AsyncSession, user_id: int, day) -> bool:
    row = await db.scalar(
        select(ExcusedDay).where(
            ExcusedDay.user_id == user_id,
            ExcusedDay.date == day,
            ExcusedDay.status == ExcusedStatus.approved.value,
        )
    )
    return row is not None


async def evaluate(db: AsyncSession, now: datetime) -> list[NudgeDecision]:
    """Barcha faol operatorlarni tekshirib nudge qarorlari ro'yxatini qaytaradi.
    Hech narsa yubormaydi — faqat qaror (yuborish chaqiruvchining ishi)."""
    from api.routers.hourly_plan import _effective_today, _to_min  # circular importdan qochish

    day = now.date()
    now_min = now.hour * 60 + now.minute
    decisions: list[NudgeDecision] = []

    users = list(
        await db.scalars(
            select(User).where(
                User.role == Role.employee.value,
                User.is_active == True,  # noqa: E712
                User.telegram_id.isnot(None),
            )
        )
    )

    for user in users:
        targets = list(
            await db.scalars(
                select(HourlyTarget).where(HourlyTarget.user_id == user.id, HourlyTarget.date == day)
            )
        )
        if not targets:
            continue  # bugunga avto-reja tuzilmagan — baholamaymiz

        # Adolat: ish oynasi/dam/tushlik/grace/sababli kun
        is_working, start, end = await _effective_today(db, user, day)
        if not is_working:
            continue
        start_min, end_min = _to_min(start), _to_min(end)
        if now_min < start_min + GRACE_MINUTES or now_min >= end_min:
            continue
        if now.hour == LUNCH_HOUR:
            continue
        if await _is_excused(db, user.id, day):
            continue

        # Shovqin nazorati
        nudges = await _nudges_today(db, user.id, day)
        if len(nudges) >= MAX_NUDGES_PER_DAY:
            continue
        if nudges and (datetime.utcnow() - nudges[0].created_at) < timedelta(minutes=COOLDOWN_MINUTES):
            continue

        actuals = list(
            await db.scalars(
                select(HourlyActual).where(HourlyActual.user_id == user.id, HourlyActual.date == day)
            )
        )
        done = sum(a.calls for a in actuals)
        answered = sum(a.answered for a in actuals)
        talk = sum(a.talk_sec for a in actuals)
        short = sum(a.short_calls for a in actuals)

        planned_so_far = 0
        frac = now.minute / 60
        for t in targets:
            if t.hour < now.hour:
                planned_so_far += t.target_calls
            elif t.hour == now.hour:
                planned_so_far += round(t.target_calls * frac)

        payload = {
            "name": user.full_name.split()[0] if user.full_name else "",
            "hour": now.hour,
            "planned_so_far": planned_so_far,
            "done_so_far": done,
            "avg_talk_sec": round(talk / answered) if answered else 0,
            "short_calls": short,
            "day_target": sum(t.target_calls for t in targets),
            "day_done": done,
        }

        # ORQADA QOLISH — sabab so'raladi
        if planned_so_far >= BEHIND_MIN_GAP and done < planned_so_far * BEHIND_RATIO \
                and (planned_so_far - done) >= BEHIND_MIN_GAP:
            decisions.append(NudgeDecision(user=user, kind="behind", ask_reason=True, payload=payload))
            continue

        # ANOMALIYA — ko'p qisqa qo'ng'iroq (miqdor joyida bo'lsa ham sifat past)
        if short >= ANOMALY_SHORT_CALLS and answered > 0 and short / answered >= ANOMALY_SHORT_RATIO:
            payload["anomaly"] = "qisqa_qongiroqlar"
            decisions.append(NudgeDecision(user=user, kind="anomaly", ask_reason=False, payload=payload))

    return decisions
