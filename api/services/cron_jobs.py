"""Cron ticklarining SOF mantiqi — HTTP qatlamisiz.

NEGA (2026-08-13, SAYT_QOTISHI_TAHLIL.md Bosqich 4b): bu ishlar ilgari FAQAT
HTTP endpoint sifatida mavjud edi va cPanel'dagi cron ularni SAYTGA so'rov
yuborib bajarardi. Deploy'da konkurentlik = 1, ya'ni har bir cron chaqiruvi
yagona Passenger ishchisini band qilib, odamlarning so'rovlarini navbatga
tiqardi. Eng chastotalisi — `group_digest_tick`, u HAR DAQIQA ishlaydi.

Endi mantiq shu yerda, ikkita chaqiruvchi bilan:
  - `api/routers/*` — HTTP endpointlar SAQLANADI (Docker/scheduler rejimi
    `scheduler/main.py` ularni hamon chaqiradi);
  - `scripts/cron_tick.py` — cPanel rejimida shu funksiyalarni O'Z
    jarayonida chaqiradi.

Bu modul ATAYLAB FastAPI'dan mustaqil: cron uni import qilganda butun web
stack ko'tarilmasin (2026-07-31 dagi uzilish aynan shundan bo'lgan).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from api.timeutil import TASHKENT_TZ
from db.models import (
    AppLoginToken,
    GroupPostConfig,
    KnowledgeEntry,
    KnowledgeStatus,
    LoginAttempt,
    TaskModel,
    TaskStatus,
    UsedTelegramLoginHash,
)

logger = logging.getLogger(__name__)


async def mark_overdue(db: AsyncSession) -> dict:
    """Muddati o'tgan `pending` vazifalarni `overdue` ga o'tkazadi.

    Muddatsiz (deadline=None) vazifalar tegilmaydi. Overdue vazifani xodim
    keyin ham «Bajardim» bilan yopa oladi."""
    result = await db.execute(
        update(TaskModel)
        .where(
            TaskModel.status == TaskStatus.pending.value,
            TaskModel.deadline.isnot(None),
            TaskModel.deadline < datetime.utcnow(),
        )
        .values(status=TaskStatus.overdue.value)
    )
    await db.commit()
    return {"marked_overdue": result.rowcount or 0}


async def cleanup_login_security(db: AsyncSession) -> dict:
    """Telegram login xavfsizligi: eskirgan replay-hash, rate-limit urinishi
    va ilova login tokenlarini o'chiradi — jadvallar cheksiz o'smasin.

    Chegara qiymatlari endpointdagi bilan AYNAN bir xil: hash 25 soat
    (24 soatlik `auth_date` oynasidan zahira bilan), urinish 1 soat (eng
    uzun oyna — dev-login 3600s), ilova tokeni 1 soat (o'zi 5 daqiqada
    eskiradi)."""
    now = datetime.utcnow()
    hash_cutoff = now - timedelta(hours=25)
    attempt_cutoff = now - timedelta(hours=1)
    app_token_cutoff = now - timedelta(hours=1)

    hash_result = await db.execute(
        delete(UsedTelegramLoginHash).where(UsedTelegramLoginHash.consumed_at < hash_cutoff)
    )
    attempt_result = await db.execute(
        delete(LoginAttempt).where(LoginAttempt.created_at < attempt_cutoff)
    )
    app_token_result = await db.execute(
        delete(AppLoginToken).where(AppLoginToken.created_at < app_token_cutoff)
    )
    await db.commit()
    return {
        "deleted_hashes": hash_result.rowcount,
        "deleted_attempts": attempt_result.rowcount,
        "deleted_app_login_tokens": app_token_result.rowcount,
    }


async def knowledge_tick(db: AsyncSession) -> dict:
    """Draft bilim yozuvlarini chegaralangan AI to'plamida qayta ishlaydi.

    Draft bo'lmasa — YENGIL no-op: AI servisi umuman import qilinmaydi
    (import funksiya ichida, aynan shu sabab)."""
    pending = await db.scalar(
        select(func.count())
        .select_from(KnowledgeEntry)
        .where(KnowledgeEntry.status == KnowledgeStatus.draft.value)
    )
    if not pending:
        return {"processed": 0, "remaining": 0}
    from api.services import knowledge as svc

    return await svc.process_batch(db)


async def get_group_config(db: AsyncSession) -> GroupPostConfig:
    """Guruhga yuborish sozlamasi (yagona qator, id=1) — yo'q bo'lsa yaratadi."""
    cfg = await db.get(GroupPostConfig, 1)
    if cfg is None:
        cfg = GroupPostConfig(id=1, post_hour=19, post_minute=10)
        db.add(cfg)
        await db.commit()
        await db.refresh(cfg)
    return cfg


async def group_digest_tick(db: AsyncSession) -> dict:
    """Kunlik lid digestini guruhga yuboradi (vaqti kelgan bo'lsa).

    `>=` semantikasi ATAYLAB: cron aynan sozlangan daqiqani o'tkazib yuborsa
    ham (restart, kechikish) keyingi tick'da baribir yuboriladi;
    `last_posted_date` qo'riqchisi bir kunda ikki marta yuborilishdan
    saqlaydi.

    HAR DAQIQA chaqiriladi — shuning uchun vaqti kelmagan holat imkon qadar
    arzon: faqat bitta `SELECT` va sana solishtiruvi."""
    cfg = await get_group_config(db)
    now = datetime.now(TASHKENT_TZ)
    today = now.date()
    due = (now.hour, now.minute) >= (cfg.post_hour, cfg.post_minute)
    if not (due and cfg.last_posted_date != today):
        return {"fired": False, "time": f"{cfg.post_hour:02d}:{cfg.post_minute:02d}"}

    from api.services.daily_digest import send_daily_digest

    result = await send_daily_digest(db)
    cfg.last_posted_date = today
    # Digest ko'rsatgan jami raqamlar — ertalabki "kecha yakuni" tuzatish
    # xabari (send_yesterday_correction) yakuniy sonlarni shu bilan
    # solishtiradi.
    totals = result.get("totals") or {}
    cfg.last_posted_calls = totals.get("calls")
    cfg.last_posted_leads = totals.get("leads")
    cfg.last_posted_visits = totals.get("visits")
    await db.commit()
    return {"fired": True, **result}
