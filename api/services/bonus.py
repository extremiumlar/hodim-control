from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.routers.norms import VIDEO_METRIC_TYPES, metrics_for
from api.routers.stats import _confirmed_videos_count
from api.services.kpi_rates import resolve_kpi_rate
from db.models import DailyResult, User

# 2026-08-08: stavkalar bu yerdan OLIB TASHLANDI.
#
# Ilgari ular shu faylda konstanta edi (PLACEHOLDER_RATE_PER_CONVERSATION =
# 2000 va h.k.). Oqibati: HR stavkani saytdan o'zgartira olmasdi (har safar
# dasturchi + deploy), stavka tarixiy emasdi va lavozimga qarab
# farqlanmasdi — mobilograf videosi stavkasi esa 0 bo'lgani uchun uning
# KPI'si doim nol chiqardi.
#
# Endi stavka `kpi_rates` jadvalidan olinadi (`resolve_kpi_rate`): 3 darajali
# (xodim > lavozim > global) va tarixiy (`effective_from`). Egasining talabi
# bo'yicha jadval BO'SH holda chiqarildi — qiymatlarni HR saytdan kiritadi.


async def calculate_bonus(db: AsyncSession, user: User, period: str) -> dict:
    """period format: "YYYY-MM". Qaytaradi: {"amount": float, "breakdown": dict}.

    Faqat xodim lavozimida kuzatiladigan ko'rsatkichlar hisobga olinadi
    (`metrics_for`) — masalan video-only mobilograf uchun suhbat/tashrif
    qo'shilmaydi.

    STAVKA SOZLANMAGAN bo'lsa o'sha ko'rsatkich uchun 0 qo'shiladi, LEKIN
    breakdown'da `rate_*: null` va `missing_rates` ro'yxati qoladi — HR
    "nega bonus 0" degan savolga bir qarashda javob topsin. Bu 0 stavka
    bilan bir xil emas: 0 — ataylab bepul, null — hali kiritilmagan.
    """
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

    amount = Decimal("0")
    missing: list[str] = []
    breakdown: dict = {
        "formula": "ko'rsatkich soni × stavka (kpi_rates: xodim > lavozim > global)",
        "period": period,
        "days_with_data": len(results),
    }

    async def _apply(metric: str, count: int) -> None:
        """Bitta ko'rsatkichni hisobga qo'shadi va breakdown'ga yozadi."""
        nonlocal amount
        # Stavka OY BOSHIGA aniqlanadi: oy o'rtasida o'zgartirilsa, o'sha oy
        # bir xil stavka bilan yakunlanadi (yarim oy u, yarim oy bu bo'lmasin).
        rate = await resolve_kpi_rate(db, user, metric, period_start)
        breakdown[f"total_{metric}"] = count
        breakdown[f"rate_{metric}"] = float(rate) if rate is not None else None
        if rate is None:
            missing.append(metric)
            return
        amount += Decimal(count) * rate

    if "suhbat" in metrics:
        await _apply("suhbat", sum(r.conversations_count for r in results))

    if "tashrif" in metrics:
        await _apply("tashrif", sum(r.visits_count for r in results))

    for metric_key, video_type in VIDEO_METRIC_TYPES.items():
        if metric_key not in metrics:
            continue
        total_videos = await _confirmed_videos_count(
            db, user.id, period_start, period_end - timedelta(days=1), video_type=video_type
        )
        await _apply(metric_key, total_videos)

    if missing:
        breakdown["missing_rates"] = missing

    return {"amount": float(amount), "breakdown": breakdown}
