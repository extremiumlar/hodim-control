"""Reklama xarajati va birlik iqtisodiyoti — voronka 3-bosqich.

Reja: `VORONKA_TARGET_REJASI.html` 03-bosqich. Savolning «rasxot» qismi:
«bitta uy sotish bizga qancha reklama puliga tushadi».

HISOBLAR:
  CPL  = xarajat ÷ lid        — bitta lid necha so'mga tushdi
  CPV  = xarajat ÷ tashrif    — bitta tashrif narxi
  CAC  = xarajat ÷ shartnoma  — bitta SOTUV narxi (asosiy raqam)
  ROMI = (shartnoma × o'rtacha foyda − xarajat) ÷ xarajat × 100%

KANAL BOG'LANISHI: `AdSpend.channel` voronkadagi kanal nomi bilan AYNAN mos
bo'lishi kerak (CRM tegi «#telegram» yoki manba «WEB_FORM»). Mos kelmasa
xarajat lidsiz qoladi — bunday qatorlar `unmatched` sifatida ALOHIDA
qaytariladi va saytda ogohlantirish bo'lib ko'rinadi. Jimgina 0 lid deb
ko'rsatish eng yomon variant bo'lardi: CPL cheksizga ketardi va hech kim
sababini bilmasdi.

KOGORTA: lid/tashrif/shartnoma sonlari `funnel.channel_funnel` dan olinadi,
ya'ni «shu oyda KELGAN lidlar» kesimida. Xarajat ham o'sha oyda qilingan —
ikkalasi bir xil to'plamga tegishli, taqqoslash halol.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.services import funnel as funnel_service
from db.models import AdSpend, FunnelMonth

# Kanal nomini solishtirishda imlo/registr farqi CPL'ni jimgina buzmasin:
# «#Telegram» va «#telegram» bitta kanal.
def _norm(channel: str) -> str:
    return (channel or "").strip().lower()


def _period_bounds(period: str) -> tuple[date, date]:
    year, month = (int(p) for p in period.split("-"))
    start = date(year, month, 1)
    end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return start, end - timedelta(days=1)


def _div(numerator: Decimal, denominator: int) -> float | None:
    """Maxraj 0 bo'lsa `None` — «hisoblab bo'lmaydi». 0 yoki cheksiz EMAS:
    «lid yo'q» bilan «lid bepul» butunlay boshqa xabar."""
    if not denominator:
        return None
    return round(float(numerator) / denominator, 1)


async def list_spend(db: AsyncSession, period: str) -> list[AdSpend]:
    return list(
        await db.scalars(
            select(AdSpend).where(AdSpend.period == period).order_by(AdSpend.channel)
        )
    )


async def upsert_spend(
    db: AsyncSession,
    period: str,
    channel: str,
    amount: float,
    reach: int | None,
    note: str | None,
    actor_id: int | None,
) -> AdSpend:
    """Oy × kanal bo'yicha xarajatni yozadi (bor bo'lsa yangilaydi).

    Nega upsert: kiritish sahifasi oyiga bir marta to'ldiriladi va rahbar
    raqamni tuzatishi odatiy hol — «allaqachon kiritilgan» xatosi bermaslik
    kerak."""
    row = await db.scalar(
        select(AdSpend).where(AdSpend.period == period, AdSpend.channel == channel)
    )
    if row is None:
        row = AdSpend(period=period, channel=channel)
        db.add(row)
    row.amount = amount
    row.reach = reach
    row.note = note
    row.updated_by = actor_id
    await db.commit()
    await db.refresh(row)
    return row


async def delete_spend(db: AsyncSession, spend_id: int) -> bool:
    row = await db.get(AdSpend, spend_id)
    if row is None:
        return False
    await db.delete(row)
    await db.commit()
    return True


async def get_month(db: AsyncSession, period: str) -> FunnelMonth | None:
    return await db.get(FunnelMonth, period)


async def set_avg_deal_profit(
    db: AsyncSession, period: str, value: float | None, actor_id: int | None
) -> FunnelMonth:
    row = await db.get(FunnelMonth, period)
    if row is None:
        row = FunnelMonth(period=period)
        db.add(row)
    row.avg_deal_profit = value
    row.updated_by = actor_id
    await db.commit()
    await db.refresh(row)
    return row


async def economics(db: AsyncSession, period: str, group_by: str = "tag") -> dict:
    """Kanal kesimida xarajat + natija + birlik iqtisodiyoti."""
    day_from, day_to = _period_bounds(period)
    today = date.today()
    channels = await funnel_service.channel_funnel(db, day_from, min(day_to, today), group_by)
    by_channel = {_norm(r["channel"]): r for r in channels["rows"]}

    month = await get_month(db, period)
    profit = Decimal(str(month.avg_deal_profit)) if month and month.avg_deal_profit else None

    rows: list[dict] = []
    unmatched: list[str] = []
    total_spend = Decimal("0")
    total_leads = total_visits = total_contracts = 0
    matched_keys: set[str] = set()

    for spend in await list_spend(db, period):
        key = _norm(spend.channel)
        stat = by_channel.get(key)
        amount = Decimal(str(spend.amount or 0))
        total_spend += amount
        leads = stat["leads"] if stat else 0
        visits = stat["visits"] if stat else 0
        contracts = stat["contracts"] if stat else 0
        if stat is None:
            unmatched.append(spend.channel)
        else:
            matched_keys.add(key)
            total_leads += leads
            total_visits += visits
            total_contracts += contracts

        rows.append(
            {
                "id": spend.id,
                "channel": spend.channel,
                "amount": float(amount),
                "reach": spend.reach,
                "note": spend.note,
                "matched": stat is not None,
                "leads": leads,
                "visits": visits,
                "contracts": contracts,
                "cpl": _div(amount, leads),
                "cpv": _div(amount, visits),
                "cac": _div(amount, contracts),
                "romi": _romi(amount, contracts, profit),
                # Qamrov kiritilgan bo'lsa — voronkaning eng yuqori bo'g'ini
                "reach_to_lead": (
                    round(leads * 100 / spend.reach, 2) if spend.reach else None
                ),
            }
        )

    # Xarajati kiritilmagan, lekin lid keltirgan kanallar — «bepul» emas,
    # shunchaki hali kiritilmagan. Rahbar nimani unutganini ko'rsin.
    missing_spend = [
        {"channel": r["channel"], "leads": r["leads"], "contracts": r["contracts"]}
        for r in channels["rows"]
        if _norm(r["channel"]) not in matched_keys
        and not r["channel"].startswith("(")
        and r["leads"] > 0
    ]

    return {
        "period": period,
        "group_by": group_by,
        "avg_deal_profit": float(profit) if profit is not None else None,
        "rows": rows,
        "unmatched": unmatched,
        "missing_spend": missing_spend[:20],
        "totals": {
            "spend": float(total_spend),
            "leads": total_leads,
            "visits": total_visits,
            "contracts": total_contracts,
            "cpl": _div(total_spend, total_leads),
            "cpv": _div(total_spend, total_visits),
            "cac": _div(total_spend, total_contracts),
            "romi": _romi(total_spend, total_contracts, profit),
        },
    }


def _romi(spend: Decimal, contracts: int, avg_profit: Decimal | None) -> float | None:
    """ROMI foizda. `avg_profit` kiritilmagan bo'lsa `None` — taxminiy
    daromad o'ylab topilmaydi."""
    if avg_profit is None or spend <= 0:
        return None
    revenue = avg_profit * Decimal(contracts)
    return round(float((revenue - spend) / spend * 100), 1)


async def missing_periods(db: AsyncSession, months: int = 3) -> list[str]:
    """Oxirgi N oy ichida xarajati UMUMAN kiritilmagan oylar (eslatma uchun).

    Joriy oy CHIQARIB TASHLANADI — u hali tugamagan, xarajatni oy oxirida
    kiritish tabiiy."""
    today = date.today()
    year, month = today.year, today.month
    out: list[str] = []
    for _ in range(months + 1):
        month -= 1
        if month == 0:
            year, month = year - 1, 12
        period = f"{year}-{month:02d}"
        exists = await db.scalar(select(AdSpend.id).where(AdSpend.period == period).limit(1))
        if exists is None:
            out.append(period)
        if len(out) >= months:
            break
    return out
