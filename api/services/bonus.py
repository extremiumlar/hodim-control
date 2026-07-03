from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import DailyResult, User

# Bonus formulasi hali kompaniya tomonidan aniqlanmagan (spetsifikatsiya 4-bo'lim).
# Quyidagi stavkalar shunchaki PLACEHOLDER — real formula kelganda faqat shu
# faylni (yoki calculate_bonus funksiyasi ichini) o'zgartirish kifoya qiladi,
# API/bot/sayt tomonidagi hech narsa o'zgarmaydi.
PLACEHOLDER_RATE_PER_CONVERSATION = 2000
PLACEHOLDER_RATE_PER_VISIT = 5000


async def calculate_bonus(db: AsyncSession, user: User, period: str) -> dict:
    """period format: "YYYY-MM". Qaytaradi: {"amount": float, "breakdown": dict}."""
    year, month = (int(part) for part in period.split("-"))
    period_start = date(year, month, 1)
    period_end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)

    results = list(
        await db.scalars(
            select(DailyResult).where(
                DailyResult.user_id == user.id,
                DailyResult.date >= period_start,
                DailyResult.date < period_end,
            )
        )
    )

    total_conversations = sum(r.conversations_count for r in results)
    total_visits = sum(r.visits_count for r in results)

    amount = (
        total_conversations * PLACEHOLDER_RATE_PER_CONVERSATION
        + total_visits * PLACEHOLDER_RATE_PER_VISIT
    )

    breakdown = {
        "formula": "placeholder: suhbatlar*stavka + tashriflar*stavka (real formula keyinroq belgilanadi)",
        "period": period,
        "days_with_data": len(results),
        "total_conversations": total_conversations,
        "total_visits": total_visits,
        "rate_per_conversation": PLACEHOLDER_RATE_PER_CONVERSATION,
        "rate_per_visit": PLACEHOLDER_RATE_PER_VISIT,
    }

    return {"amount": float(amount), "breakdown": breakdown}
