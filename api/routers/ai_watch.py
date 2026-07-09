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
from api.services import ai_coach, auto_plan, watch_rules, weekly_stats
from api.telegram_notify import inline_keyboard, send_message
from api.timeutil import TASHKENT_TZ
from db.models import AiConfig, Role, ShortfallReason, User
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


async def _get_ai_config(db: AsyncSession) -> AiConfig:
    """Yagona (id=1) runtime sozlama qatori — bo'lmasa defaultlar bilan yaratiladi."""
    cfg = await db.get(AiConfig, 1)
    if cfg is None:
        cfg = AiConfig(id=1)
        db.add(cfg)
        await db.commit()
        await db.refresh(cfg)
    return cfg


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
    cfg = await _get_ai_config(db)
    if (not settings.ai_nudge_enabled or not cfg.nudges_enabled) and not dry_run:
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


# ─── Rahbar boshqaruvi (runtime sozlamalar) ─────────────────────────────────────
_MANAGER_ROLES = (Role.hr.value, Role.rop.value, Role.boss.value, Role.dasturchi.value)


def _config_out(cfg: AiConfig) -> dict:
    return {
        "nudges_enabled": cfg.nudges_enabled,
        "group_summary_enabled": cfg.group_summary_enabled,
        "weekly_enabled": cfg.weekly_enabled,
        "summary_hour": cfg.summary_hour,
        "summary_minute": cfg.summary_minute,
        # env bosh kalitlari — bot holatni to'liq ko'rsata olishi uchun
        "ai_enabled": settings.ai_enabled,
        "push_enabled": settings.ai_nudge_enabled,
        "provider": settings.ai_provider,
    }


@router.get("/config/{telegram_id}")
async def get_config(telegram_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    """Rahbarlar uchun joriy AI sozlamalari (bot /ai_sozlama ko'rsatadi)."""
    actor = await db.scalar(select(User).where(User.telegram_id == telegram_id))
    if not actor or actor.role not in _MANAGER_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Bu amal faqat rahbarlar uchun")
    return _config_out(await _get_ai_config(db))


class ConfigIn(BaseModel):
    nudges_enabled: bool | None = None
    group_summary_enabled: bool | None = None
    weekly_enabled: bool | None = None
    summary_hour: int | None = None
    summary_minute: int | None = None


@router.post("/config/{telegram_id}")
async def set_config(telegram_id: int, payload: ConfigIn, db: AsyncSession = Depends(get_db)) -> dict:
    """AI qismlarini yoqish/o'chirish va xulosa vaqtini o'zgartirish — faqat
    Boshliq/Dasturchi (odam-qaror tamoyili: AI'ni rahbar boshqaradi)."""
    actor = await db.scalar(select(User).where(User.telegram_id == telegram_id))
    if not actor or actor.role not in (Role.boss.value, Role.dasturchi.value):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Sozlamani faqat Boshliq o'zgartira oladi")

    cfg = await _get_ai_config(db)
    if payload.summary_hour is not None and not (0 <= payload.summary_hour <= 23):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Soat 0-23 oralig'ida bo'lishi kerak")
    if payload.summary_minute is not None and not (0 <= payload.summary_minute <= 59):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Daqiqa 0-59 oralig'ida bo'lishi kerak")

    for field in ("nudges_enabled", "group_summary_enabled", "weekly_enabled", "summary_hour", "summary_minute"):
        value = getattr(payload, field)
        if value is not None:
            setattr(cfg, field, value)
    await db.commit()
    await db.refresh(cfg)
    return _config_out(cfg)


# ─── Kun yakuni xulosasini guruhga yuborish ─────────────────────────────────────
@router.post("/summary-tick")
async def summary_tick(db: AsyncSession = Depends(get_db)) -> dict:
    """Scheduler har daqiqa chaqiradi: sozlangan vaqt kelganda kun yakuni AI
    xulosasini guruhga yuboradi (`summary_last_posted` qo'riqchi — kuniga bir marta)."""
    if not settings.ai_enabled or not settings.ai_nudge_enabled:
        return {"fired": False, "disabled": True}
    cfg = await _get_ai_config(db)
    if not cfg.group_summary_enabled:
        return {"fired": False, "off": True}
    if not settings.telegram_group_chat_id:
        return {"fired": False, "no_group": True}

    now = datetime.now(TASHKENT_TZ)
    today = now.date()
    if not (now.hour == cfg.summary_hour and now.minute == cfg.summary_minute and cfg.summary_last_posted != today):
        return {"fired": False, "time": f"{cfg.summary_hour:02d}:{cfg.summary_minute:02d}"}

    from api.routers.ai_coach import group_summary  # circular importdan qochish

    result = await group_summary(db)
    ok = await send_message(settings.telegram_group_chat_id, f"📊 <b>Kun yakuni</b>\n\n{result['text']}")
    cfg.summary_last_posted = today
    await db.commit()
    return {"fired": True, "delivered": ok is not None, "source": result["source"]}


# ─── Haftalik trend ─────────────────────────────────────────────────────────────
@router.post("/weekly-run")
async def weekly_run(dry_run: bool = False, db: AsyncSession = Depends(get_db)) -> dict:
    """Haftalik trend xulosalari: har operatorga shaxsiy xabar + guruhga jamoa
    ko'rinishi. Scheduler yakshanba kechqurun chaqiradi; `weekly_last_posted`
    qo'riqchi bir haftada ikki marta yuborilishdan saqlaydi. dry_run — yubormasdan
    matnlarni qaytaradi."""
    if not settings.ai_enabled:
        return {"disabled": True}
    cfg = await _get_ai_config(db)
    if (not settings.ai_nudge_enabled or not cfg.weekly_enabled) and not dry_run:
        return {"sent": 0, "weekly_disabled": True}

    today = datetime.now(TASHKENT_TZ).date()
    if not dry_run and cfg.weekly_last_posted == today:
        return {"sent": 0, "already_posted": True}

    payloads = await weekly_stats.build_weekly_payloads(db, today)
    results = []
    sent = 0
    team_lines = []
    for user, payload in payloads:
        r = await ai_coach.weekly_trend(db, user.id, payload)
        item = {"user_id": user.id, "name": user.full_name, "source": r["source"], "text": r["text"]}
        if not dry_run:
            ok = await send_message(user.telegram_id, f"📈 <b>Haftalik xulosa</b>\n\n{r['text']}")
            item["delivered"] = ok is not None
            if ok is not None:
                sent += 1
        results.append(item)
        # Jamoa ko'rinishi — qo'shimcha AI chaqiruvsiz, kod jamlaydi
        t0, t1 = payload.get("talk_start_sec"), payload.get("talk_end_sec")
        trend = f"{t0}s→{t1}s" if (t0 is not None and t1 is not None) else "—"
        weak = f", zaif: {payload['weak_slot']}" if payload.get("weak_slot") else ""
        team_lines.append(f"• {payload['name']}: suhbat {trend}, kuniga ~{payload['calls_avg']} qo'ng'iroq{weak}")

    group_delivered = None
    if team_lines and not dry_run and settings.telegram_group_chat_id:
        text = "📈 <b>Haftalik jamoa ko'rinishi</b>\n\n" + "\n".join(team_lines)
        group_delivered = (await send_message(settings.telegram_group_chat_id, text)) is not None

    if not dry_run:
        cfg.weekly_last_posted = today
        await db.commit()

    return {
        "operators": len(payloads), "sent": sent, "dry_run": dry_run,
        "group_delivered": group_delivered, "results": results, "team_lines": team_lines,
    }
