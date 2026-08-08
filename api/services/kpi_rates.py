"""KPI stavkasini aniqlash — 3 darajali va tarixiy.

Naqsh ATAYLAB mavjud ikkitasidan yig'ilgan:
- `FinePolicy` (`payroll.resolve_policy`) dan — qamrov: xodim > lavozim >
  global. Bir daraja topilmasa keyingi (kengroq) darajaga o'tiladi.
- `SalaryRate` (`payroll.resolve_rate`) dan — tarixiylik: `effective_from
  <= sana` bo'yicha eng so'nggisi. Stavka o'zgarsa o'tgan oy bonusi
  o'zgarmaydi.

Ikkalasi birga kerak, chunki KPI stavkasi ham lavozimga bog'liq
(mobilograf va sotuvchi bir xil bo'lolmaydi), ham vaqt o'tishi bilan
o'zgaradi (indeksatsiya).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import KpiRate, User


async def _rate_for_scope(
    db: AsyncSession, scope: str, scope_id: int | None, metric: str, on_date: date
) -> KpiRate | None:
    q = select(KpiRate).where(
        KpiRate.scope == scope,
        KpiRate.metric == metric,
        KpiRate.effective_from <= on_date,
        KpiRate.deleted_at.is_(None),
    )
    q = q.where(KpiRate.scope_id.is_(None) if scope_id is None else KpiRate.scope_id == scope_id)
    return await db.scalar(q.order_by(KpiRate.effective_from.desc()).limit(1))


async def resolve_kpi_rate(
    db: AsyncSession, user: User, metric: str, on_date: date
) -> Decimal | None:
    """Shu xodim, shu ko'rsatkich uchun amaldagi stavka.

    `None` — stavka SOZLANMAGAN. Chaqiruvchi buni 0 deb talqin qiladi, lekin
    0 stavka bilan ARALASHTIRMASLIGI kerak: birinchisi "hali kiritilmagan"
    (breakdown'da shunday ko'rsatiladi), ikkinchisi "ataylab bepul".
    """
    for scope, scope_id in (
        ("user", user.id),
        ("position", user.position_id),
        ("global", None),
    ):
        if scope == "position" and scope_id is None:
            continue  # lavozimsiz xodim — bu darajani o'tkazib yuboramiz
        row = await _rate_for_scope(db, scope, scope_id, metric, on_date)
        if row is not None:
            return Decimal(str(row.amount))
    return None
