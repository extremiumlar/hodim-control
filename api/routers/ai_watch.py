"""Operator AI — real-vaqt halqasi endpointlari (4-bosqich).

`/tick` — scheduler har soat chaqiradi: yangi snapshot → arzon qoidalar
(watch_rules) → trigger bo'lganlarga AI nudge + (orqada bo'lsa) sabab so'rovi
tugmalari. Joyida bo'lganlarga JIM (faqat-kerakda-gapir).

`/reason` — bot callback'dan: operator bosgan sabab tugmasi `shortfall_reason`ga
yoziladi (bir soatga bitta, qayta bosilsa yangilanadi)."""
from datetime import date as date_type
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import settings
from api.deps import get_db, verify_bot_secret
from api.services import ai_coach, auto_plan, watch_rules
from api.telegram_notify import inline_keyboard, send_message
from api.timeutil import TASHKENT_TZ
from db.models import ShortfallReason, User
from db.upsert import upsert

router = APIRouter(prefix="/ai-watch", tags=["ai-watch"], dependencies=[Depends(verify_bot_secret)])

# Sabab tugmalari — yorliqlar shu yerda (bot faqat kodni qaytaradi, yorliqni API beradi).
REASONS: dict[str, str] = {
    "no_answer": "Mijozlar ko'tarmadi",
    "no_base": "Baza tugadi",
    "tech": "Texnik muammo",
    "meeting": "Yig'ilishda edim",
    "other": "Boshqa",
}


def _reason_keyboard(day: date_type, hour: int) -> dict:
    # callback_data: "sfr:<YYYY-MM-DD>:<soat>:<kod>" (64 baytdan ancha kichik)
    rows, row = [], []
    for code, label in REASONS.items():
        row.append((label, f"sfr:{day.isoformat()}:{hour}:{code}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return inline_keyboard(rows)


@router.post("/tick")
async def tick(dry_run: bool = False, db: AsyncSession = Depends(get_db)) -> dict:
    """Soatlik kuzatuv: snapshot → qoidalar → kerak bo'lganlarga nudge.
    `dry_run=true` — yubormasdan qarorlar/matnlarni qaytaradi (sinov uchun).
    AI o'chiq bo'lsa no-op; AI yoqiq lekin AI_NUDGE_ENABLED o'chiq bo'lsa faqat
    dry_run rejimida ishlaydi (haqiqiy push alohida opt-in)."""
    if not settings.ai_enabled:
        return {"disabled": True}
    if not settings.ai_nudge_enabled and not dry_run:
        return {"sent": 0, "nudge_disabled": True}

    now = datetime.now(TASHKENT_TZ)
    # Yangi ma'lumot bilan baholash — bugungi snapshot yengil (early-stop skan)
    await auto_plan.snapshot_hourly_actual(db, now.date())

    decisions = await watch_rules.evaluate(db, now)
    results = []
    sent = 0
    for d in decisions:
        text_result = await ai_coach.coach_nudge(db, d.user.id, d.payload)
        item = {
            "user_id": d.user.id,
            "name": d.user.full_name,
            "kind": d.kind,
            "ask_reason": d.ask_reason,
            "source": text_result["source"],
            "text": text_result["text"],
        }
        if not dry_run:
            markup = _reason_keyboard(now.date(), now.hour) if d.ask_reason else None
            ok = await send_message(d.user.telegram_id, text_result["text"], reply_markup=markup)
            item["delivered"] = ok is not None
            if ok is not None:
                sent += 1
        results.append(item)

    return {
        "at": f"{now.hour:02d}:{now.minute:02d}",
        "date": now.date().isoformat(),
        "evaluated": True,
        "triggered": len(decisions),
        "sent": sent,
        "dry_run": dry_run,
        "results": results,
    }


class ReasonIn(BaseModel):
    telegram_id: int
    date: str  # YYYY-MM-DD (callback_data'dan)
    hour: int
    code: str


@router.post("/reason")
async def save_reason(payload: ReasonIn, db: AsyncSession = Depends(get_db)) -> dict:
    """Operator bosgan sabab tugmasini yozadi. Bir (user, kun, soat)ga bitta sabab —
    qayta bosilsa yangilanadi. Yorliqni qaytaradi (bot tasdiqda ko'rsatadi)."""
    label = REASONS.get(payload.code)
    if label is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Noma'lum sabab kodi")
    user = await db.scalar(select(User).where(User.telegram_id == payload.telegram_id))
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Foydalanuvchi topilmadi")

    day = date_type.fromisoformat(payload.date)
    stmt = upsert(ShortfallReason).values(user_id=user.id, date=day, hour=payload.hour, reason=label)
    stmt = stmt.on_conflict_do_update(
        index_elements=["user_id", "date", "hour"], set_={"reason": stmt.excluded.reason}
    )
    await db.execute(stmt)
    await db.commit()
    return {"label": label}
