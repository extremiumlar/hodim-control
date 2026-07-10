"""Operator AI — issiq lid (speed-to-lead, 5-bosqich). Bu KOD, AI emas: tezlik
muhim bo'lgani uchun matnlar shablon, tashqi modelga murojaat yo'q.

Oqim (har tick):
  1. ANIQLASH — CRM'dan oxirgi oynada yaratilgan lidlar o'qiladi; bazadagi eng
     katta `crm_lead_id` (watermark)dan yangilari "issiq lid" deb qayd etiladi.
     Birinchi ishga tushishda mavjud lidlar `baseline` sifatida jimgina yoziladi
     (eski lidlar uchun spam bo'lmasin).
  2. XABAR — CRM tayinlagan operator (`responsibleById` →
     `users.crm_visit_external_id`) ga darhol DM: kontakt ismi, telefon, manba +
     "Qabul qildim" tugmasi. Mos operator topilmasa guruhga tushadi (egasiz lid
     ko'rinmay qolmasin). Taqsimotni CRM qiladi — biz buzmaymiz.
  3. BIRINCHI QO'NG'IROQ — javob kutayotgan lidlar uchun call-history'dan
     (phoneSearch) lid raqamiga birinchi ALOQA qo'ng'irog'i izlanadi (chiquvchi —
     urinish kifoya, yoki kiruvchi javob berilgan); topilsa
     speed-to-lead sekundi yozilib yakunlanadi (status=called).
  4. ESKALATSIYA — ish soatlarida ESCALATE_AFTER_MINUTES dan beri qo'ng'iroqsiz
     turgan lid guruhga chiqariladi (qo'llab-quvvatlovchi ohang + real oqibat).

Yozuvdagi uch vaqt farqi metrika beradi: yaratilish→aniqlash (tizim), aniqlash→
qabul (reaksiya), yaratilish→birinchi qo'ng'iroq (haqiqiy speed-to-lead)."""
import logging
import time
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import settings
from api.telegram_notify import inline_keyboard, send_message
from api.timeutil import TASHKENT_TZ
from crm import get_crm_adapter
from db.models import HotLead, User

logger = logging.getLogger(__name__)

# Aniqlash oynasi: watermark asosiy filtr, oyna faqat so'rovni kichik tutadi.
# 6 soat — scheduler uzoq o'chib qolsa ham oradagi lidlar yo'qolmasin.
LOOKBACK_SECONDS = 6 * 3600
# Qabul muddati: lid tushgandan shuncha daqiqa ichida CRM'da aloqa qo'ng'irog'i
# (chiquvchi urinish yoki kiruvchi javob berilgan) ko'rinmasa — kechikkan
# hisoblanadi va guruhga eskalatsiya. "Qabul" mezoni HAQIQIY qo'ng'iroq
# (call-history phoneSearch), Telegram tugmasi emas — tugmani bosib qo'ng'iroq
# qilmagan operator ham shu yerda ushlanadi.
ESCALATE_AFTER_MINUTES = 5
# Eskalatsiya faqat shu mahalliy soat oralig'ida (kechasi kelgan lid uchun
# operatorni ayblamaymiz — adolat tamoyili).
ESCALATE_HOUR_FROM, ESCALATE_HOUR_TO = 8, 21
# Bir tick'da nechta lidga birinchi-qo'ng'iroq tekshiruvi (rate limit himoyasi:
# har tekshiruv bitta CRM so'rovi).
FIRST_CALL_CHECKS_PER_TICK = 10
# Shuncha soatdan keyin birinchi qo'ng'iroqni izlashni to'xtatamiz (eski lid).
FIRST_CALL_GIVE_UP_HOURS = 72
# Qo'ng'iroq lid yaratilishidan OLDIN ham bo'lishi mumkin: MOI_ZVONKI kabi
# manbalarda lid aynan qo'ng'iroqdan keyin avto-yaraladi (jonli misol: qo'ng'iroq
# liddan 27s oldin — 13547494). Shu oynadagi oldingi qo'ng'iroq ham "qabul"
# hisoblanadi (first_call_sec 0 ga qisqartiriladi), soxta eskalatsiya bo'lmaydi.
PRE_CREATION_GRACE_SECONDS = 10 * 60


def _adapter():
    return get_crm_adapter(settings.crm_type)


def _lead_label(lead: HotLead) -> str:
    return lead.contact_name or lead.lead_name or f"lid #{lead.crm_lead_id}"


def _notify_text(lead: HotLead) -> str:
    lines = ["🔥 <b>Yangi issiq lid!</b>"]
    if lead.contact_name:
        lines.append(f"👤 {lead.contact_name}")
    if lead.phone:
        lines.append(f"📞 {lead.phone}")
    if lead.source:
        lines.append(f"🌐 Manba: {lead.source}")
    lines.append("")
    lines.append(
        f"⏱ {ESCALATE_AFTER_MINUTES} daqiqa ichida qo'ng'iroq qiling — birinchi daqiqalarda lid eng issiq bo'ladi. "
        "Qo'ng'iroq CRM'dan avtomatik tekshiriladi, kechikkani guruhga chiqadi."
    )
    return "\n".join(lines)


async def _map_users_by_crm_id(db: AsyncSession) -> dict[str, User]:
    users = await db.scalars(select(User).where(User.crm_visit_external_id.isnot(None)))
    return {u.crm_visit_external_id: u for u in users}


async def detect_and_notify(db: AsyncSession, dry_run: bool) -> dict:
    adapter = _adapter()
    if adapter is None:
        return {"error": "crm_yoq"}

    now_ts = int(time.time())
    leads = await adapter.get_leads_created_between(now_ts - LOOKBACK_SECONDS, now_ts)
    if leads is None:
        return {"error": "crm_xato"}

    watermark = await db.scalar(select(func.max(HotLead.crm_lead_id)))

    # Birinchi ishga tushish: mavjud lidlar baseline — xabarsiz yoziladi, shundan
    # keyingi har bir yangi ID haqiqiy "issiq lid" bo'ladi.
    if watermark is None:
        if not dry_run:
            for item in leads:
                db.add(
                    HotLead(
                        crm_lead_id=item["id"],
                        lead_name=item.get("name"),
                        responsible_crm_id=item.get("responsible_id"),
                        created_ts=item.get("created_ts") or now_ts,
                        status="baseline",
                    )
                )
            await db.commit()
        return {"seeded": len(leads)}

    fresh = sorted((l for l in leads if l["id"] > watermark), key=lambda l: l["id"])
    if not fresh:
        return {"new": 0}

    # Watermark'dan katta bo'lsa ham allaqachon yozilganlarni himoya qilamiz
    # (parallel tick/qayta urinish holati).
    existing = set(
        await db.scalars(select(HotLead.crm_lead_id).where(HotLead.crm_lead_id.in_([l["id"] for l in fresh])))
    )
    fresh = [l for l in fresh if l["id"] not in existing]

    users_by_crm = await _map_users_by_crm_id(db)
    results = []
    for item in fresh:
        detail = await adapter.get_lead_detail(item["id"]) or {}
        responsible_id = detail.get("responsible_id") or item.get("responsible_id")
        user = users_by_crm.get(str(responsible_id)) if responsible_id is not None else None

        lead = HotLead(
            crm_lead_id=item["id"],
            lead_name=detail.get("name") or item.get("name"),
            contact_name=detail.get("contact_name"),
            phone=detail.get("phone"),
            source=detail.get("source"),
            responsible_crm_id=responsible_id,
            user_id=user.id if user else None,
            created_ts=item.get("created_ts") or now_ts,
            status="notified",
        )

        entry = {
            "crm_lead_id": item["id"],
            "contact": lead.contact_name,
            "phone": lead.phone,
            "operator": user.full_name if user else None,
            "text": _notify_text(lead),
        }
        if not dry_run:
            db.add(lead)
            await db.flush()  # tugma callback_data uchun lead.id kerak
            delivered = None
            if user and user.telegram_id:
                markup = inline_keyboard([[("✅ Qabul qildim", f"hl:{lead.id}")]])
                delivered = await send_message(user.telegram_id, _notify_text(lead), reply_markup=markup)
            elif settings.telegram_group_chat_id:
                # Mas'ul tizimda topilmadi — lid ko'rinmay qolmasin, guruhga
                text = _notify_text(lead) + "\n\n⚠️ Mas'ul operator tizimda topilmadi — kim oladi?"
                delivered = await send_message(settings.telegram_group_chat_id, text)
            lead.notified_at = datetime.utcnow()
            entry["delivered"] = delivered is not None
        results.append(entry)

    if not dry_run:
        await db.commit()
    return {"new": len(results), "results": results}


async def check_first_calls(db: AsyncSession, dry_run: bool) -> dict:
    adapter = _adapter()
    if adapter is None:
        return {"checked": 0}

    cutoff = datetime.utcnow() - timedelta(hours=FIRST_CALL_GIVE_UP_HOURS)
    pending = list(
        await db.scalars(
            select(HotLead)
            .where(
                HotLead.status.in_(("notified", "claimed")),
                HotLead.first_call_at.is_(None),
                HotLead.phone.isnot(None),
                HotLead.detected_at >= cutoff,
            )
            .order_by(HotLead.detected_at)
            .limit(FIRST_CALL_CHECKS_PER_TICK)
        )
    )

    found = []
    for lead in pending:
        call_ts = await adapter.find_first_contact_call(
            lead.phone, lead.created_ts - PRE_CREATION_GRACE_SECONDS
        )
        if call_ts is None:
            continue
        speed_sec = max(0, call_ts - lead.created_ts)
        entry = {"crm_lead_id": lead.crm_lead_id, "speed_sec": speed_sec}
        if not dry_run:
            lead.first_call_at = datetime.utcfromtimestamp(call_ts)
            lead.first_call_sec = speed_sec
            lead.status = "called"
        found.append(entry)

    if found and not dry_run:
        await db.commit()
    return {"checked": len(pending), "called": found}


async def escalate_stale(db: AsyncSession, dry_run: bool) -> dict:
    now_local = datetime.now(TASHKENT_TZ)
    if not (ESCALATE_HOUR_FROM <= now_local.hour < ESCALATE_HOUR_TO):
        return {"escalated": 0, "off_hours": True}

    # Muddat lid CRM'da YARATILGAN paytdan sanaladi (created_ts) — first_call_sec
    # bilan bir xil boshlanish nuqtasi, "tizim kech aniqladi" degan yumshoqlik yo'q.
    threshold_ts = int(time.time()) - ESCALATE_AFTER_MINUTES * 60
    stale = list(
        await db.scalars(
            select(HotLead).where(
                HotLead.status.in_(("notified", "claimed")),
                HotLead.first_call_at.is_(None),
                HotLead.escalated_at.is_(None),
                HotLead.created_ts <= threshold_ts,
            )
        )
    )

    escalated = []
    for lead in stale:
        minutes = int((int(time.time()) - lead.created_ts) // 60)
        operator = None
        if lead.user_id:
            operator = await db.get(User, lead.user_id)
        who = operator.full_name if operator else "mas'ul topilmadi"
        text = (
            "⚠️ <b>Issiq lid kechikdi</b>\n"
            f"👤 {_lead_label(lead)} — lid tushganiga {minutes} daqiqa bo'ldi, "
            f"qo'ng'iroq hali yo'q ({ESCALATE_AFTER_MINUTES} daqiqalik qabul muddati o'tdi).\n"
            f"Mas'ul: {who}. Keling, sovib qolmasin — hoziroq bog'lanaylik."
        )
        entry = {"crm_lead_id": lead.crm_lead_id, "operator": who, "minutes": minutes, "text": text}
        if not dry_run:
            if settings.telegram_group_chat_id:
                await send_message(settings.telegram_group_chat_id, text)
            lead.escalated_at = datetime.utcnow()
        escalated.append(entry)

    if escalated and not dry_run:
        await db.commit()
    return {"escalated": len(escalated), "results": escalated}


async def tick(db: AsyncSession, dry_run: bool = False) -> dict:
    """Bitta to'liq aylanish: aniqlash+xabar → birinchi qo'ng'iroq → eskalatsiya.
    dry_run — hech narsa yozmaydi/yubormaydi, faqat nima bo'lishini qaytaradi."""
    detect = await detect_and_notify(db, dry_run)
    first_calls = await check_first_calls(db, dry_run)
    escalation = await escalate_stale(db, dry_run)
    return {"dry_run": dry_run, "detect": detect, "first_calls": first_calls, "escalation": escalation}
