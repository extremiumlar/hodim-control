"""Operator AI — haftalik trend agregatlari (6-bosqich). Bu KOD: raqamlarni shu
yer hisoblaydi, `ai_coach.weekly_trend` faqat tayyor payload'dan matn yozadi.

Taqqoslash: "shu hafta" = ref_day bilan tugaydigan 7 kun, "o'tgan hafta" = undan
oldingi 7 kun. Signallar:
  - talk_start_sec / talk_end_sec: o'tgan hafta vs shu hafta o'rtacha suhbat
    (javob berilgan qo'ng'iroqqa sekund) — o'sish/pasayish trendi;
  - calls_avg: shu haftada faoliyatli kunlarga o'rtacha qo'ng'iroq;
  - weak_slot: shu haftada eng past qo'ng'iroqli hafta kuni (kamida 2 faoliyatli
    kun bo'lsa) — "payshanba kuni zaif" ko'rinishida."""
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import HourlyActual, Role, User

WEEKDAYS_UZ = ["dushanba", "seshanba", "chorshanba", "payshanba", "juma", "shanba", "yakshanba"]


def _avg_talk(rows: list[HourlyActual]) -> int | None:
    answered = sum(r.answered for r in rows)
    if not answered:
        return None
    return round(sum(r.talk_sec for r in rows) / answered)


async def build_weekly_payloads(db: AsyncSession, ref_day: date) -> list[tuple[User, dict]]:
    """Har bir faol operator uchun (user, payload) ro'yxati. Shu haftada umuman
    faoliyati bo'lmagan operator tashlanadi (ta'tilda bo'lishi mumkin — jim)."""
    this_start = ref_day - timedelta(days=6)
    prev_start = this_start - timedelta(days=7)
    prev_end = this_start - timedelta(days=1)

    users = list(
        await db.scalars(
            select(User).where(
                User.role == Role.employee.value,
                User.is_active == True,  # noqa: E712
                User.telegram_id.isnot(None),
            )
        )
    )

    results: list[tuple[User, dict]] = []
    for user in users:
        this_rows = list(
            await db.scalars(
                select(HourlyActual).where(
                    HourlyActual.user_id == user.id,
                    HourlyActual.date >= this_start,
                    HourlyActual.date <= ref_day,
                )
            )
        )
        if not this_rows or not sum(r.calls for r in this_rows):
            continue

        prev_rows = list(
            await db.scalars(
                select(HourlyActual).where(
                    HourlyActual.user_id == user.id,
                    HourlyActual.date >= prev_start,
                    HourlyActual.date <= prev_end,
                )
            )
        )

        # Kunlar kesimida jami qo'ng'iroq — o'rtacha va zaif kun uchun
        per_day: dict[date, int] = {}
        for r in this_rows:
            per_day[r.date] = per_day.get(r.date, 0) + r.calls
        active_days = {d: c for d, c in per_day.items() if c > 0}
        calls_avg = round(sum(active_days.values()) / len(active_days)) if active_days else 0

        weak_slot = None
        if len(active_days) >= 2:
            weak_day = min(active_days, key=lambda d: active_days[d])
            # eng past kun o'rtachadan sezilarli (25%+) past bo'lsagina "zaif" deymiz
            if active_days[weak_day] < calls_avg * 0.75:
                weak_slot = f"{WEEKDAYS_UZ[weak_day.weekday()]} kuni"

        payload = {
            "name": user.full_name.split()[0] if user.full_name else "",
            "talk_start_sec": _avg_talk(prev_rows),
            "talk_end_sec": _avg_talk(this_rows),
            "calls_avg": calls_avg,
            "weak_slot": weak_slot,
            "week_start": this_start.isoformat(),
            "week_end": ref_day.isoformat(),
        }
        results.append((user, payload))
    return results
