"""Voronka qoidalari — panelda boshqariladigan sozlamalar.

TZ ning 0-bosqichi «bekor qilingan shartnoma va sifatsiz lid qanday
sanaladi» degan ta'rifni talab qilgan edi. Javob KODDA QOTIRILMAYDI: bu
biznes qarori va vaqt o'tib o'zgarishi mumkin, shuning uchun panelda
yoqib-o'chiriladi (`FunnelSettings`, yagona qator id=1).

DEFAULT — IKKALASI HAM O'CHIQ: sozlama qo'shilishi bilan mavjud raqamlar
o'zgarib ketmasin. Rahbar ongli ravishda yoqadi va o'sha lahzadan boshlab
hisob o'zgaradi (tarix qayta hisoblanmaydi — voronka har safar jonli
o'qiydi, ya'ni yoqilgach barcha davrlar yangi qoida bilan ko'rinadi).
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import CrmLeadState, FunnelSettings, LeadEvent


async def get_settings(db: AsyncSession) -> FunnelSettings:
    """Sozlama qatori (bo'lmasa — yaratiladi, ikkalasi ham o'chiq holda)."""
    row = await db.get(FunnelSettings, 1)
    if row is None:
        row = FunnelSettings(id=1)
        db.add(row)
        await db.commit()
        await db.refresh(row)
    return row


async def update_settings(db: AsyncSession, payload: dict, actor_id: int | None) -> FunnelSettings:
    row = await get_settings(db)
    for field in (
        "cancelled_pipe_status_ids",
        "subtract_cancelled",
        "low_quality_pipe_status_ids",
        "exclude_low_quality",
    ):
        if field in payload and payload[field] is not None:
            value = payload[field]
            if field.endswith("_ids"):
                value = [int(v) for v in value] or None
            setattr(row, field, value)
    row.updated_by = actor_id
    await db.commit()
    await db.refresh(row)
    return row


async def known_stages(db: AsyncSession) -> list[dict]:
    """CRM bosqichlari ro'yxati — panelda tanlash uchun.

    CRM'ga so'rov YUBORMAYDI: nomlar bizning jurnalimizda allaqachon bor
    (`lead_events.to_stage_name` va `crm_lead_state.stage_name`). Shuning
    uchun bu ro'yxat bepul va Uysot limitiga tegmaydi."""
    seen: dict[int, str] = {}
    for rows in (
        await db.execute(
            select(LeadEvent.to_pipe_status_id, LeadEvent.to_stage_name).distinct()
        ),
        await db.execute(
            select(CrmLeadState.pipe_status_id, CrmLeadState.stage_name).distinct()
        ),
    ):
        for pipe_id, name in rows:
            if pipe_id is not None and name:
                seen.setdefault(int(pipe_id), name)
    return [
        {"pipe_status_id": pid, "name": name}
        for pid, name in sorted(seen.items(), key=lambda kv: kv[1].lower())
    ]


async def rules(db: AsyncSession) -> dict:
    """Hisob uchun tayyor qoidalar (voronka yadrosi shuni o'qiydi).

    Bosqich ID'lari BO'SH bo'lsa qoida yoqilgan bo'lsa ham ishlamaydi —
    aks holda «yoqdim, lekin hech nima o'zgarmadi» degan jim holat paydo
    bo'lardi. Panel buni ogohlantirish bilan ko'rsatadi."""
    row = await get_settings(db)
    cancelled = set(row.cancelled_pipe_status_ids or [])
    low_quality = set(row.low_quality_pipe_status_ids or [])
    return {
        "subtract_cancelled": bool(row.subtract_cancelled and cancelled),
        "cancelled_ids": cancelled,
        "exclude_low_quality": bool(row.exclude_low_quality and low_quality),
        "low_quality_ids": low_quality,
    }
