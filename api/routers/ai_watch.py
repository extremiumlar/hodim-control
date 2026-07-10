"""Operator AI — real-vaqt halqasi endpointlari (4-bosqich, 7-bosqichda erkin matn).

`/tick` — scheduler har soat chaqiradi: yangi snapshot → arzon qoidalar
(watch_rules) → trigger bo'lganlarga AI nudge + (orqada bo'lsa) sababini ERKIN
MATN bilan yozish so'rovi (pending yozuv ochiladi). Joyida bo'lganlarga JIM.

`/reason-text` — bot operator yozgan matnni yuboradi: AI tasniflaydi
(`ai_coach.classify_reason_text`), tekshiriladigan da'volarni KOD faktlar bilan
solishtiradi ("lid tugadi" → CRM'dagi ochiq lidlar soni, "ko'tarmadi" → bugungi
terilgan raqamlar), natija `shortfall_reason`ga yoziladi. Da'vo faktlarga zid
chiqsa rahbarlarga darhol xabar ketadi — operator alday olmaydi.

`/reason` — ESKI tugma oqimi (orqaga moslik: oldin yuborilgan tugmali xabarlar
bosilsa ishlayveradi)."""
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
from crm import get_crm_adapter
from db.models import AiConfig, HourlyActual, HourlyTarget, Role, ShortfallReason, User
from db.upsert import upsert

router = APIRouter(prefix="/ai-watch", tags=["ai-watch"], dependencies=[Depends(verify_bot_secret)])

# Eski tugma oqimi yorliqlari (faqat orqaga moslik uchun — yangi nudge'lar tugmasiz).
REASONS: dict[str, str] = {
    "no_answer": "Mijozlar ko'tarmadi",
    "no_base": "Baza tugadi",
    "tech": "Texnik muammo",
    "meeting": "Yig'ilishda edim",
    "other": "Boshqa",
}

# Nudge ostiga qo'shiladigan yo'riqnoma — operator sababini o'z so'zlari bilan yozadi.
_ASK_REASON_SUFFIX = (
    "\n\n✍️ Sababini shu chatga qisqacha yozib yuboring — tizim tahlil qilib rahbarga yetkazadi."
)


async def _get_ai_config(db: AsyncSession) -> AiConfig:
    """Yagona (id=1) runtime sozlama qatori — bo'lmasa defaultlar bilan yaratiladi."""
    cfg = await db.get(AiConfig, 1)
    if cfg is None:
        cfg = AiConfig(id=1)
        db.add(cfg)
        await db.commit()
        await db.refresh(cfg)
    return cfg


async def _open_pending_reason(db: AsyncSession, user_id: int, day: date_type, hour: int) -> None:
    """Sabab so'ralganda kutish (pending, reason=NULL) yozuvini ochadi — bot kelgan
    erkin matnni aynan shu soatga bog'laydi. Shu soatga sabab allaqachon yozilgan
    bo'lsa ustidan yozilmaydi (do_nothing)."""
    stmt = upsert(ShortfallReason).values(user_id=user_id, date=day, hour=hour)
    stmt = stmt.on_conflict_do_nothing(index_elements=["user_id", "date", "hour"])
    await db.execute(stmt)
    await db.commit()


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
            text = text_result["text"]
            if d.ask_reason:
                text += _ASK_REASON_SUFFIX
                await _open_pending_reason(db, d.user.id, now.date(), now.hour)
            ok = await send_message(d.user.telegram_id, text)
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


# ─── Erkin matnli sabab: AI tasnif + fakt tekshiruvi ────────────────────────────
# "Ko'tarmadi" da'vosi uchun urinish chegaralari: terilgan raqamlar rejaning shu
# ulushidan ko'p bo'lsa da'vo ishonchli, ozidan kam bo'lsa faktlarga zid.
_DIALED_OK_RATIO = 0.7
_DIALED_SUSPECT_RATIO = 0.5


class ReasonTextIn(BaseModel):
    telegram_id: int
    text: str


async def _today_effort(db: AsyncSession, user_id: int, day: date_type, upto_hour: int) -> dict:
    """Operatorning bugungi urinish faktlari: terilgan raqamlar (javobsizlar ham),
    javob berilganlar va sabab so'ralgan soatgacha bo'lgan reja."""
    actuals = list(
        await db.scalars(select(HourlyActual).where(HourlyActual.user_id == user_id, HourlyActual.date == day))
    )
    targets = list(
        await db.scalars(select(HourlyTarget).where(HourlyTarget.user_id == user_id, HourlyTarget.date == day))
    )
    return {
        "calls_dialed": sum(a.calls for a in actuals),
        "answered": sum(a.answered for a in actuals),
        "planned_so_far": sum(t.target_calls for t in targets if t.hour <= upto_hour),
    }


async def _verify_claim(db: AsyncSession, user: User, category: str, effort: dict) -> tuple[bool | None, str | None]:
    """Da'voni FAKTLAR bilan solishtiradi (AI emas — kod hukm chiqaradi).
    Qaytaradi: (verified, izoh). verified: True — tasdiqlandi, False — zid
    (ehtimoliy aldash), None — tekshirib bo'lmaydi/ma'lumot yetarli emas."""
    if category == "no_base":
        # "Lid/baza tugadi" — CRM'dan operatorga biriktirilgan ochiq lidlar sanaladi
        adapter = get_crm_adapter(settings.crm_type)
        if adapter is None or not user.crm_visit_external_id:
            return None, "CRM tekshiruvi imkonsiz (CRM yoki operator ID sozlanmagan)"
        count = await adapter.count_open_leads(user.crm_visit_external_id)
        if count is None:
            return None, "CRM tekshiruvi imkonsiz (ochiq lid bosqichlari sozlanmagan yoki CRM xatosi)"
        if count == 0:
            return True, "CRM tasdiqladi: biriktirilgan ochiq lid qolmagan"
        return False, f"CRM'da operatorga biriktirilgan {count} ta ochiq lid bor"

    if category == "no_answer":
        # "Mijozlar ko'tarmadi" — javob mijozga bog'liq, lekin TERISH operatorga
        # bog'liq: raqam yetarlicha terilganmi shuni tekshiramiz.
        planned = effort["planned_so_far"]
        dialed = effort["calls_dialed"]
        if planned <= 0:
            return None, None
        if dialed >= planned * _DIALED_OK_RATIO:
            return True, f"{dialed} ta raqam terilgan ({effort['answered']} ta javob) — urinish yetarli"
        if dialed < planned * _DIALED_SUSPECT_RATIO:
            return False, f"reja {planned} bo'lgan vaqtgacha faqat {dialed} ta raqam terilgan — urinishning o'zi kam"
        return None, f"{dialed} ta raqam terilgan (reja {planned}) — chegara holat"

    # tech/meeting/other — avtomatik tekshirib bo'lmaydi, rahbar ko'radi
    return None, None


async def _alert_managers(db: AsyncSession, user: User, hour: int, raw_text: str, label: str, note: str) -> None:
    """Da'vo faktlarga zid chiqqanda rahbarlarga (boss + rop) darhol DM — "odam-qaror"
    tamoyili: AI ayblamaydi, faktni rahbarga ko'rsatadi, xulosani odam chiqaradi."""
    managers = list(
        await db.scalars(
            select(User).where(
                User.role.in_((Role.boss.value, Role.rop.value)),
                User.is_active == True,  # noqa: E712
                User.telegram_id.isnot(None),
            )
        )
    )
    text = (
        "⚠️ <b>Sabab tekshiruvi mos kelmadi</b>\n\n"
        f"👤 {user.full_name}\n"
        f"🕐 Soat {hour:02d}:00 atrofidagi orqada qolish\n"
        f"💬 Yozgan sababi: «{raw_text[:200]}» ({label})\n"
        f"🔎 Tekshiruv: {note}"
    )
    for m in managers:
        await send_message(m.telegram_id, text)


async def _request_manager_confirmation(db: AsyncSession, user: User, row: ShortfallReason) -> int:
    """Avtomatik tekshirib bo'lmagan (verified=None) sababni ROPlarga (yo'q bo'lsa
    Boshliqqa) tasdiqlash tugmalari bilan yuboradi — hukm odamda qoladi. Bir necha
    rahbar olsa, birinchi bosgani hal qiladi (qolganlarga "hal bo'lgan" ko'rinadi).
    Qaytaradi: nechta rahbarga yetkazildi."""
    managers = list(
        await db.scalars(
            select(User).where(
                User.role == Role.rop.value,
                User.is_active == True,  # noqa: E712
                User.telegram_id.isnot(None),
            )
        )
    )
    if not managers:
        managers = list(
            await db.scalars(
                select(User).where(
                    User.role == Role.boss.value,
                    User.is_active == True,  # noqa: E712
                    User.telegram_id.isnot(None),
                )
            )
        )
    auto_note = f"\n🔎 Avto-tekshiruv: {row.verify_note}" if row.verify_note else ""
    text = (
        "🔎 <b>Sababni tasdiqlash kerak</b>\n\n"
        f"👤 {user.full_name}\n"
        f"🕐 Soat {row.hour:02d}:00 atrofidagi orqada qolish\n"
        f"💬 Yozgan sababi: «{(row.raw_text or '')[:200]}» ({row.reason})"
        f"{auto_note}\n\n"
        "Bu sabab to'g'rimi? (CRM'dan avtomatik tekshirib bo'lmadi)"
    )
    markup = inline_keyboard([[("✅ Tasdiqlash", f"sfv:{row.id}:1"), ("❌ Rad etish", f"sfv:{row.id}:0")]])
    sent = 0
    for m in managers:
        if (await send_message(m.telegram_id, text, reply_markup=markup)) is not None:
            sent += 1
    return sent


@router.post("/reason-text")
async def save_reason_text(payload: ReasonTextIn, db: AsyncSession = Depends(get_db)) -> dict:
    """Operator botga yozgan erkin matnli sababni qabul qiladi. Faqat KUTILAYOTGAN
    (bugun nudge yuborilib pending ochilgan) operator uchun ishlaydi — aks holda
    {"handled": false} (bot matnni e'tiborsiz qoldiradi, boshqa oqimlarga xalal yo'q).

    Oqim: AI tasnif → kod/CRM fakt tekshiruvi → yozuvni to'ldirish → operatorga
    javob matni. Da'vo faktlarga zid bo'lsa rahbarlarga ogohlantirish; avtomatik
    tekshirib BO'LMAGAN sabab esa ROPga tasdiqlash tugmalari bilan boradi."""
    user = await db.scalar(select(User).where(User.telegram_id == payload.telegram_id))
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Foydalanuvchi topilmadi")

    text = payload.text.strip()
    if not text:
        return {"handled": False}

    today = datetime.now(TASHKENT_TZ).date()
    # Kunning BARCHA ochiq so'rovlari olinadi: bot o'chiq turgan/operator kechikkan
    # holatda bir kunda bir nechta javobsiz so'rov yig'ilib qolishi mumkin — bitta
    # javob hammasini yopadi (aks holda digestda "Sabab yozilmagan" bo'lib adolatsiz
    # ko'rinadi). Tahlil eng oxirgi (eng dolzarb) soat kontekstida qilinadi.
    pendings = list(
        await db.scalars(
            select(ShortfallReason)
            .where(
                ShortfallReason.user_id == user.id,
                ShortfallReason.date == today,
                ShortfallReason.reason.is_(None),
            )
            .order_by(ShortfallReason.hour.desc())
        )
    )
    if not pendings:
        return {"handled": False}
    pending = pendings[0]

    classification = await ai_coach.classify_reason_text(text)
    effort = await _today_effort(db, user.id, today, pending.hour)
    verified, note = await _verify_claim(db, user, classification["category"], effort)

    answered_at = datetime.utcnow()
    for row in pendings:
        row.reason = classification["label"]
        row.raw_text = text[:1000]
        row.ai_category = classification["category"]
        row.verified = verified
        row.verify_note = note
        row.answered_at = answered_at
    await db.commit()

    # Avtomatik hukm chiqmagan sabab rahbarga (ROP) tasdiqlashga boradi
    manager_sent = 0
    if verified is None:
        manager_sent = await _request_manager_confirmation(db, user, pending)

    reply = await ai_coach.reason_reply(
        db,
        user.id,
        {
            "name": user.full_name.split()[0] if user.full_name else "",
            "label": classification["label"],
            "raw_text": text[:300],
            "verified": verified,
            "verify_note": note,
            "pending_manager": manager_sent > 0,
            **effort,
        },
    )

    if verified is False:
        await _alert_managers(db, user, pending.hour, text, classification["label"], note or "")

    return {
        "handled": True,
        "reply": reply["text"],
        "label": classification["label"],
        "verified": verified,
        "verify_note": note,
        "manager_confirmations_sent": manager_sent,
    }


class ReasonVerifyIn(BaseModel):
    telegram_id: int  # qaror qilayotgan rahbar
    reason_id: int
    approve: bool


@router.post("/reason-verify")
async def verify_reason(payload: ReasonVerifyIn, db: AsyncSession = Depends(get_db)) -> dict:
    """Rahbar (ROP/Boshliq/Dasturchi) operator sababini tasdiqlaydi yoki rad etadi —
    avtomatik tekshirib bo'lmagan da'volar uchun yakuniy hukm odamniki. Birinchi
    qaror yakuniy: keyingi bosishlarga {"already": true} qaytadi. Rad etilsa
    operatorga ham xabar boradi (kun yakunida "mos kelmadi" bo'lib ko'rinadi)."""
    actor = await db.scalar(select(User).where(User.telegram_id == payload.telegram_id))
    if not actor or actor.role not in (Role.rop.value, Role.boss.value, Role.dasturchi.value):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Bu amal faqat ROP/Boshliq uchun")

    row = await db.get(ShortfallReason, payload.reason_id)
    if row is None or row.reason is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sabab yozuvi topilmadi")
    if row.verified is not None:
        return {"already": True, "verified": row.verified, "verify_note": row.verify_note}

    actor_name = actor.full_name.split()[0] if actor.full_name else "Rahbar"
    decision_note = f"Rahbar {actor_name} {'tasdiqladi' if payload.approve else 'rad etdi'}"
    row.verified = payload.approve
    row.verify_note = f"{row.verify_note} • {decision_note}" if row.verify_note else decision_note
    await db.commit()

    # Operatorga qaror haqida xabar
    operator = await db.get(User, row.user_id)
    if operator and operator.telegram_id:
        if payload.approve:
            op_text = f"✅ Rahbar sababingizni tasdiqladi: <b>{row.reason}</b>. Bu sizning aybingiz emas deb qayd etildi."
        else:
            op_text = (
                f"❌ Rahbar «{row.reason}» sababini rad etdi. Iltimos, ishni davom ettiring — "
                "bu holat kun yakuni xulosasida ko'rinadi."
            )
        await send_message(operator.telegram_id, op_text)

    return {"already": False, "verified": row.verified, "verify_note": row.verify_note, "label": row.reason}


# ─── Rahbar boshqaruvi (runtime sozlamalar) ─────────────────────────────────────
_MANAGER_ROLES = (Role.hr.value, Role.rop.value, Role.boss.value, Role.dasturchi.value)


def _config_out(cfg: AiConfig) -> dict:
    # summary_hour/minute endi ishlatilmaydi: AI xulosa kunlik digest ichida chiqadi,
    # digest vaqtini esa GroupPostConfig (/statistika_vaqt) boshqaradi.
    return {
        "nudges_enabled": cfg.nudges_enabled,
        "group_summary_enabled": cfg.group_summary_enabled,
        "weekly_enabled": cfg.weekly_enabled,
        "hot_leads_enabled": cfg.hot_leads_enabled,
        # env bosh kalitlari — bot holatni to'liq ko'rsata olishi uchun
        "ai_enabled": settings.ai_enabled,
        "push_enabled": settings.ai_nudge_enabled,
        "hot_lead_push_enabled": settings.hot_lead_enabled,
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
    hot_leads_enabled: bool | None = None


@router.post("/config/{telegram_id}")
async def set_config(telegram_id: int, payload: ConfigIn, db: AsyncSession = Depends(get_db)) -> dict:
    """AI qismlarini yoqish/o'chirish — faqat Boshliq/Dasturchi (odam-qaror
    tamoyili: AI'ni rahbar boshqaradi). Kun yakuni AI xulosasining alohida vaqti
    yo'q — u kunlik digest bilan birga chiqadi (vaqt: /statistika_vaqt)."""
    actor = await db.scalar(select(User).where(User.telegram_id == telegram_id))
    if not actor or actor.role not in (Role.boss.value, Role.dasturchi.value):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Sozlamani faqat Boshliq o'zgartira oladi")

    cfg = await _get_ai_config(db)
    for field in ("nudges_enabled", "group_summary_enabled", "weekly_enabled", "hot_leads_enabled"):
        value = getattr(payload, field)
        if value is not None:
            setattr(cfg, field, value)
    await db.commit()
    await db.refresh(cfg)
    return _config_out(cfg)


# Eslatma: eski /summary-tick endpointi olib tashlandi — kun yakuni AI xulosasi
# endi kunlik digest ichida chiqadi (api/services/daily_digest.py, vaqti
# GroupPostConfig'dan /statistika_vaqt bilan boshqariladi).


# ─── Haftalik trend ─────────────────────────────────────────────────────────────
@router.post("/weekly-run")
async def weekly_run(dry_run: bool = False, db: AsyncSession = Depends(get_db)) -> dict:
    """Haftalik AI trend xulosalari: har operatorga SHAXSIY xabar (suhbat trendi,
    zaif kun). Guruhga jamoa ko'rinishini endi raqamli haftalik digest beradi
    (/reports/weekly-digest — scheduler alohida yuboradi, AI'siz ham ishlaydi),
    shuning uchun bu yerdan guruhga hech narsa yuborilmaydi. `weekly_last_posted`
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
    for user, payload in payloads:
        r = await ai_coach.weekly_trend(db, user.id, payload)
        item = {"user_id": user.id, "name": user.full_name, "source": r["source"], "text": r["text"]}
        if not dry_run:
            ok = await send_message(user.telegram_id, f"📈 <b>Haftalik xulosa</b>\n\n{r['text']}")
            item["delivered"] = ok is not None
            if ok is not None:
                sent += 1
        results.append(item)

    if not dry_run:
        cfg.weekly_last_posted = today
        await db.commit()

    return {"operators": len(payloads), "sent": sent, "dry_run": dry_run, "results": results}
