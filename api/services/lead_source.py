"""Lid manbasini (attribution kanali) sekin-asta to'ldirish — voronka 2-bosqich.

NEGA ALOHIDA VA SEKIN: manba (`MOI_ZVONKI`, `FACEBOOK_FORM`, `telegram`...)
ommaviy `/lead/filter` javobida YO'Q — faqat `GET /lead/{id}` detalida. Ya'ni
har bir lid uchun BITTA so'rov. Uysot limiti — 60 so'rov/daqiqa va u
diff-skaner, issiq lid, qo'ng'iroq tarixi bilan BO'LISHILADI. 10 000 lidni
bir yo'la so'rash 429 bo'roniga olib kelardi (2026-07 da bir marta bo'lgan,
`uysot-rate-budget` xotirasiga qarang).

Shuning uchun: har tick'da ATIGI `LEAD_SOURCE_BATCH` ta lid so'raladi, eng
yangisidan boshlab. `source_checked_at` — qayta so'ramaslik izi: manba
topilmasa ham qo'yiladi, aks holda bir xil «manbasiz» lid har tick'da
so'ralaverardi.

Teglar (`CrmLeadState.tags`) bunga MUHTOJ EMAS — ular ommaviy skanerda bepul
keladi va kanal kesimining asosiy manbai o'sha (`funnel.py`).
"""
from __future__ import annotations

import logging
import os
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import CrmLeadState

logger = logging.getLogger(__name__)

# Bir tick'da nechta lid manbasi so'raladi. 20 × har 5 daqiqa ≈ 240/soat —
# CRM byudjetining kichik ulushi (limit 3600/soat).
LEAD_SOURCE_BATCH = int(os.getenv("LEAD_SOURCE_BATCH", "20") or 20)
# 0 bo'lsa boyitish umuman o'chiq (masalan token muammosi paytida).
ENABLED = LEAD_SOURCE_BATCH > 0


def _adapter():
    from crm import get_crm_adapter
    from api.config import settings

    adapter = get_crm_adapter(settings.crm_type)
    return adapter if adapter is not None and hasattr(adapter, "get_lead_detail") else None


async def enrich_tick(db: AsyncSession, limit: int | None = None) -> dict:
    """Manbasi hali so'ralmagan lidlardan bir nechtasini boyitadi.

    Eng YANGI lidlardan boshlanadi: yangi ma'lumot kundalik hisobga darhol
    kerak, eski arxiv esa kutib tura oladi."""
    if not ENABLED:
        return {"ok": True, "skipped": "o'chiq (LEAD_SOURCE_BATCH=0)"}

    adapter = _adapter()
    if adapter is None:
        return {"ok": False, "reason": "CRM sozlanmagan"}

    batch = limit if limit is not None else LEAD_SOURCE_BATCH
    rows = list(
        await db.scalars(
            select(CrmLeadState)
            .where(CrmLeadState.source_checked_at.is_(None))
            .order_by(CrmLeadState.crm_lead_id.desc())
            .limit(batch)
        )
    )
    if not rows:
        return {"ok": True, "checked": 0, "found": 0, "remaining": 0}

    now = datetime.utcnow()
    found = 0
    for row in rows:
        try:
            detail = await adapter.get_lead_detail(row.crm_lead_id)
        except Exception:  # noqa: BLE001 — bitta lid butun tick'ni yiqitmasin
            logger.exception("Lid manbasini olishda xato (lead_id=%s)", row.crm_lead_id)
            break
        # `detail is None` — lid o'chirilgan yoki CRM xatosi. Baribir belgilaymiz:
        # aks holda shu lid har tick'da qayta so'ralib byudjetni yeb turardi.
        row.source_checked_at = now
        if detail and detail.get("source"):
            row.source = str(detail["source"])[:64]
            found += 1

    await db.commit()

    remaining = await db.scalar(
        select(CrmLeadState.crm_lead_id)
        .where(CrmLeadState.source_checked_at.is_(None))
        .limit(1)
    )
    return {
        "ok": True,
        "checked": len(rows),
        "found": found,
        "has_more": remaining is not None,
    }
