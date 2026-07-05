from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.routers.norms import metrics_for
from api.routers.stats import _confirmed_videos_count
from db.models import DailyResult, User

# Bonus formulasi hali kompaniya tomonidan aniqlanmagan (spetsifikatsiya 4-bo'lim).
# Quyidagi stavkalar shunchaki PLACEHOLDER — real formula kelganda faqat shu
# faylni (yoki calculate_bonus funksiyasi ichini) o'zgartirish kifoya qiladi,
# API/bot/sayt tomonidagi hech narsa o'zgarmaydi.
PLACEHOLDER_RATE_PER_CONVERSATION = 2000
PLACEHOLDER_RATE_PER_VISIT = 5000
# Video stavkasi hali belgilanmagan — 0 bo'lsa ham video soni breakdown'da
# ko'rinadi (mobilograf ishi "ko'rinmas" bo'lib qolmasligi uchun); stavka
# belgilanganda faqat shu konstantani o'zgartirish yetarli.
PLACEHOLDER_RATE_PER_VIDEO = 0


async def calculate_bonus(db: AsyncSession, user: User, period: str) -> dict:
    """period format: "YYYY-MM". Qaytaradi: {"amount": float, "breakdown": dict}.
    Faqat xodim lavozimida kuzatiladigan ko'rsatkichlar hisobga olinadi
    (metrics_for) — masalan video-only mobilograf uchun suhbat/tashrif
    qo'shilmaydi, buning o'rniga video soni breakdown'da ko'rinadi."""
    year, month = (int(part) for part in period.split("-"))
    period_start = date(year, month, 1)
    period_end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)

    metrics = metrics_for(user)

    results = list(
        await db.scalars(
            select(DailyResult).where(
                DailyResult.user_id == user.id,
                DailyResult.date >= period_start,
                DailyResult.date < period_end,
            )
        )
    )

    amount = 0
    breakdown: dict = {
        "formula": "placeholder: lavozim metrikalari * stavka (real formula keyinroq belgilanadi)",
        "period": period,
        "days_with_data": len(results),
    }

    if "suhbat" in metrics:
        total_conversations = sum(r.conversations_count for r in results)
        amount += total_conversations * PLACEHOLDER_RATE_PER_CONVERSATION
        breakdown["total_conversations"] = total_conversations
        breakdown["rate_per_conversation"] = PLACEHOLDER_RATE_PER_CONVERSATION

    if "tashrif" in metrics:
        total_visits = sum(r.visits_count for r in results)
        amount += total_visits * PLACEHOLDER_RATE_PER_VISIT
        breakdown["total_visits"] = total_visits
        breakdown["rate_per_visit"] = PLACEHOLDER_RATE_PER_VISIT

    if "video" in metrics:
        total_videos = await _confirmed_videos_count(
            db, user.id, period_start, period_end - timedelta(days=1)
        )
        amount += total_videos * PLACEHOLDER_RATE_PER_VIDEO
        breakdown["total_videos"] = total_videos
        breakdown["rate_per_video"] = PLACEHOLDER_RATE_PER_VIDEO

    return {"amount": float(amount), "breakdown": breakdown}
