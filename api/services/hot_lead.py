"""Operator AI — issiq lid (speed-to-lead, 5-bosqich). Bu KOD, AI emas: tezlik
muhim bo'lgani uchun matnlar shablon, tashqi modelga murojaat yo'q.

Oqim (har tick):
  1. ANIQLASH — CRM'dan oxirgi oynada yaratilgan lidlar o'qiladi; bazadagi eng
     katta `crm_lead_id` (watermark)dan yangilari "issiq lid" deb qayd etiladi.
     Birinchi ishga tushishda mavjud lidlar `baseline` sifatida jimgina yoziladi
     (eski lidlar uchun spam bo'lmasin).
  2. XABAR — CRM tayinlagan operator (`responsibleById` →
     `users.crm_visit_external_id`) ga darhol DM: kontakt ismi, telefon, manba.
     Mos operator topilmasa guruhga tushadi (egasiz lid ko'rinmay qolmasin).
     Taqsimotni CRM qiladi — biz buzmaymiz. Qabul TUGMASI YO'Q — operator
     hech narsa bosishi shart emas, "qabul" mezoni har doim HAQIQIY qo'ng'iroq
     (4-bandga qarang), tugma faqat qo'shimcha ish qadami bo'lardi (2026-07-22
     olib tashlandi: eski xabarlardagi tugma hali ishlaydi — orqaga moslik
     uchun `/hot-lead/claim` endpointi va bot callback'i saqlanadi, faqat
     ENDI YANGI xabarlarga tugma qo'shilmaydi).
  3. CRM HOLATI SINXRONI — diff-engine (`lead_diff.py`) allaqachon to'plagan
     `CrmLeadState`dan (qo'shimcha CRM so'rovisiz): mas'ul BOSHQA operatorga
     o'tkazilgan bo'lsa yozuv yangi mas'ulga ko'chiriladi (eski operator endi
     ayblanmaydi); bosqich TERMINAL (spam/rad/dublikat — qo'ng'iroqsiz qonuniy
     yopilish) holatga o'tgan bo'lsa eskalatsiya to'xtaydi.
  4. BIRINCHI QO'NG'IROQ — javob kutayotgan lidlar uchun call-history'dan
     (phoneSearch) lidning BARCHA ma'lum raqamlariga birinchi ALOQA qo'ng'irog'i
     izlanadi (chiquvchi — urinish kifoya, yoki kiruvchi javob berilgan); topilsa
     speed-to-lead sekundi yozilib yakunlanadi (status=called). Tekshirilgan
     har lid `last_call_check_at`ni oladi — bu eskalatsiyaning navbat-xavfsizlik
     belgisi (5-bandga qarang).
  5. ESKALATSIYA — ish soatlarida, FAQAT hech bo'lmasa bir marta tekshirilgan
     (`last_call_check_at`) va operator ISHDA (davomat check-in/check-out'i
     bilan tasdiqlangan) lidlar uchun ESCALATE_AFTER_MINUTES dan beri
     qo'ng'iroqsiz tursa guruhga chiqariladi.
  6. TUZATISH — eskalatsiya qilingan lid KEYINCHALIK qo'ng'iroq bilan yoki
     qonuniy sabab bilan yopilsa, guruhga avtomatik tuzatuvchi xabar — yolg'on
     signal jim qolib ketmaydi.

Yozuvdagi uch vaqt farqi metrika beradi: yaratilish→aniqlash (tizim), aniqlash→
qabul (reaksiya), yaratilish→birinchi qo'ng'iroq (haqiqiy speed-to-lead)."""
import logging
import time
from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import settings
from api.telegram_notify import send_message
from api.timeutil import TASHKENT_TZ
from crm import get_crm_adapter
from crm.config import CRM_UYSOT_HOT_LEAD_TERMINAL_PIPE_STATUS_IDS
from db.models import Attendance, CrmLeadState, HotLead, MonitoredGroup, User

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
# har tekshiruv bitta CRM so'rovi — endi lid boshiga bir nechta raqam bo'lgani
# uchun MAX_PHONES_PER_LEAD_CHECK bilan ham cheklanadi).
FIRST_CALL_CHECKS_PER_TICK = 10
MAX_PHONES_PER_LEAD_CHECK = 3
# Shuncha soatdan keyin birinchi qo'ng'iroqni izlashni to'xtatamiz (eski lid).
FIRST_CALL_GIVE_UP_HOURS = 72
# Qo'ng'iroq lid yaratilishidan OLDIN ham bo'lishi mumkin: MOI_ZVONKI kabi
# manbalarda lid aynan qo'ng'iroqdan keyin avto-yaraladi (jonli misol: qo'ng'iroq
# liddan 27s oldin — 13547494). Shu oynadagi oldingi qo'ng'iroq ham "qabul"
# hisoblanadi (first_call_sec 0 ga qisqartiriladi), soxta eskalatsiya bo'lmaydi.
PRE_CREATION_GRACE_SECONDS = 10 * 60
# Mas'ul-o'tkazish DM'lari va tuzatish xabarlari — YANGI kuzatuv (bu tizim
# ishga tushirilgunga qadar to'plangan ESKI "ochiq"/"eskalatsiya qilingan"
# yozuvlar bo'yicha emas). Bir tickda shu sondan ko'p nomzod chiqsa — bu haqiqiy
# "shu daqiqada" hodisa emas, orqada qolgan tarixiy backlog (jonli tekshiruvda
# 198 tagacha, kunlar oldingi) deb hisoblanadi: holat baribir yangilanadi
# (to'g'ri son/status saqlanishi uchun), lekin xabar YUBORILMAYDI — aks holda
# guruh/DM kunlar oldingi voqealar bilan to'lib ketardi. Kichik/haqiqiy oqim
# (kunlik bir nechta hodisa) har doim normal xabar bilan o'tadi.
NOTIFY_BACKLOG_THRESHOLD = 5


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


async def _main_group_chat_id(db: AsyncSession) -> int | None:
    """"main" maqsadli faol guruh (`MonitoredGroup`, dasturchi botdan
    `/guruh_biriktir main` bilan boshqaradi) — mas'ul topilmaganda yoki
    eskalatsiya/tuzatish xabari uchun zaxira manzil."""
    return await db.scalar(
        select(MonitoredGroup.chat_id).where(
            MonitoredGroup.purpose == "main", MonitoredGroup.is_active == True  # noqa: E712
        )
    )


async def _map_users_by_crm_id(db: AsyncSession) -> dict[str, User]:
    users = await db.scalars(select(User).where(User.crm_visit_external_id.isnot(None)))
    return {u.crm_visit_external_id: u for u in users}


async def _lead_states_by_id(db: AsyncSession, crm_lead_ids: list[int]) -> dict[int, CrmLeadState]:
    if not crm_lead_ids:
        return {}
    rows = await db.scalars(select(CrmLeadState).where(CrmLeadState.crm_lead_id.in_(crm_lead_ids)))
    return {r.crm_lead_id: r for r in rows}


async def _operator_absent_reason(db: AsyncSession, user_id: int) -> str | None:
    """Operator hozir ishda emasligi sababi (yoki `None` — ishda/tasdiqlanmagan).
    Kelib-ketish yozuvidan: hali check-in qilmagan (kelmagan) yoki check-out
    qilib ulgurgan (ketgan) — ikkalasida ham "kechikdi" deb ayblash adolatsiz."""
    today = datetime.now(TASHKENT_TZ).date()
    att = await db.scalar(
        select(Attendance).where(Attendance.user_id == user_id, Attendance.date == today)
    )
    if att is None or att.check_in_time is None:
        return "hali ishga kelmagan (check-in yo'q)"
    if att.check_out_time is not None:
        return "ishdan ketgan (check-out qilingan)"
    return None


async def sync_crm_state(db: AsyncSession, dry_run: bool) -> dict:
    """CRM'dagi mas'ul/bosqich o'zgarishini diff-engine `CrmLeadState`sidan
    (qo'shimcha CRM so'rovisiz, lokal) o'qib, hali ochiq issiq lidlarga qo'llaydi:

      - mas'ul BOSHQA operatorga o'tgan bo'lsa — yozuv yangi mas'ulga
        ko'chiriladi (eski operator endi eskalatsiyada ayblanmaydi) va yangi
        operator DM oladi (original xabar eskisiga ketgan edi);
      - bosqich TERMINAL (`CRM_UYSOT_HOT_LEAD_TERMINAL_PIPE_STATUS_IDS` —
        spam/rad/dublikat kabi qo'ng'iroqsiz qonuniy yopilish) holatga o'tgan
        bo'lsa — `resolved_no_call`, eskalatsiya to'xtaydi.

    `CrmLeadState` bu lidni hali "ko'rmagan" bo'lishi mumkin (diff-engine 5
    daqiqalik sikl) — bunda hech narsa qilinmaydi, keyingi tick qayta tekshiradi."""
    open_leads = list(
        await db.scalars(select(HotLead).where(HotLead.status.in_(("notified", "claimed"))))
    )
    if not open_leads:
        return {"checked": 0, "reassigned": 0, "resolved": 0}

    states = await _lead_states_by_id(db, [l.crm_lead_id for l in open_leads])
    if not states:
        return {"checked": len(open_leads), "reassigned": 0, "resolved": 0}
    users_by_crm = await _map_users_by_crm_id(db)

    # Nechta lidda haqiqiy drift bor — shu asosda backlog/oqim qaror qilinadi
    # (pastga qarang, NOTIFY_BACKLOG_THRESHOLD izohi).
    drift_count = sum(
        1
        for lead in open_leads
        if (state := states.get(lead.crm_lead_id)) is not None
        and state.responsible_id is not None
        and state.responsible_id != lead.responsible_crm_id
    )
    is_backlog = drift_count > NOTIFY_BACKLOG_THRESHOLD

    reassigned: list[dict] = []
    resolved: list[dict] = []
    for lead in open_leads:
        state = states.get(lead.crm_lead_id)
        if state is None:
            continue

        if state.pipe_status_id in CRM_UYSOT_HOT_LEAD_TERMINAL_PIPE_STATUS_IDS:
            resolved.append({"crm_lead_id": lead.crm_lead_id, "stage": state.stage_name})
            if not dry_run:
                lead.status = "resolved_no_call"
                lead.resolved_reason = state.stage_name
            continue

        if state.responsible_id is not None and state.responsible_id != lead.responsible_crm_id:
            new_user = users_by_crm.get(str(state.responsible_id))
            reassigned.append(
                {
                    "crm_lead_id": lead.crm_lead_id,
                    "from": lead.responsible_crm_id,
                    "to": state.responsible_id,
                    "new_operator": new_user.full_name if new_user else None,
                }
            )
            if not dry_run:
                lead.responsible_crm_id = state.responsible_id
                lead.user_id = new_user.id if new_user else None
                lead.reassigned_at = datetime.utcnow()
                if not is_backlog and new_user and new_user.telegram_id:
                    await send_message(
                        new_user.telegram_id,
                        _notify_text(lead) + "\n\n↪️ Bu lid sizga CRM'da o'tkazildi.",
                    )

    if not dry_run and (reassigned or resolved):
        await db.commit()
    return {
        "checked": len(open_leads),
        "reassigned": len(reassigned),
        "resolved": len(resolved),
        "reassigned_list": reassigned,
        "resolved_list": resolved,
    }


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
    main_chat_id = await _main_group_chat_id(db)
    results = []
    for item in fresh:
        detail = await adapter.get_lead_detail(item["id"]) or {}
        responsible_id = detail.get("responsible_id") or item.get("responsible_id")
        user = users_by_crm.get(str(responsible_id)) if responsible_id is not None else None

        phone = detail.get("phone")
        phones = detail.get("phones") or ([phone] if phone else None)
        lead = HotLead(
            crm_lead_id=item["id"],
            lead_name=detail.get("name") or item.get("name"),
            contact_name=detail.get("contact_name"),
            phone=phone,
            phones=phones,
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
                delivered = await send_message(user.telegram_id, _notify_text(lead))
            elif main_chat_id:
                # Mas'ul tizimda topilmadi — lid ko'rinmay qolmasin, guruhga
                text = _notify_text(lead) + "\n\n⚠️ Mas'ul operator tizimda topilmadi — kim oladi?"
                delivered = await send_message(main_chat_id, text)
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
    now_dt = datetime.utcnow()
    for lead in pending:
        # Mijozning BARCHA ma'lum raqamlari tekshiriladi — operator ikkinchi/
        # uchinchi raqamga qo'ng'iroq qilgan bo'lishi mumkin (faqat birinchisini
        # tekshirish doimiy yolg'on signal manbai edi).
        numbers = (lead.phones or ([lead.phone] if lead.phone else []))[:MAX_PHONES_PER_LEAD_CHECK]
        earliest_ts: int | None = None
        for number in numbers:
            call_ts = await adapter.find_first_contact_call(
                number, lead.created_ts - PRE_CREATION_GRACE_SECONDS
            )
            if call_ts is not None and (earliest_ts is None or call_ts < earliest_ts):
                earliest_ts = call_ts

        if not dry_run:
            # Tekshirilgani (topilmagan bo'lsa ham) qayd etiladi — eskalatsiyaning
            # navbat-xavfsizlik belgisi: hali tekshirilmagan lid eskalatsiya
            # qilinmaydi (pastga qarang).
            lead.last_call_check_at = now_dt

        if earliest_ts is None:
            continue
        # Ba'zi operator qurilmalarining soati noto'g'ri — call-history'da
        # KELAJAKDAGI startStamp ko'rilgan (jonli misol: +5-10 soat siljigan).
        # Yozuv borligi "aloqa bo'ldi" faktini beradi, lekin tezlik metrikasi
        # buzilmasligi uchun hozirgi vaqtdan yuqorisi kesiladi.
        call_ts = min(earliest_ts, int(time.time()))
        speed_sec = max(0, call_ts - lead.created_ts)
        entry = {"crm_lead_id": lead.crm_lead_id, "speed_sec": speed_sec}
        if not dry_run:
            lead.first_call_at = datetime.utcfromtimestamp(call_ts)
            lead.first_call_sec = speed_sec
            lead.status = "called"
        found.append(entry)

    if pending and not dry_run:
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
                # Navbat-xavfsizlik: hali BIR MARTA HAM tekshirilmagan lid
                # eskalatsiya qilinmaydi — aks holda backlog (FIRST_CALL_CHECKS_
                # PER_TICK cheklovi) paytida "hali tekshirmadik" bilan "haqiqatan
                # kechikdi" farqlanmay, operator aslida ulgurgan bo'lsa ham
                # yolg'on eskalatsiya chiqishi mumkin edi.
                HotLead.last_call_check_at.isnot(None),
                HotLead.created_ts <= threshold_ts,
            )
        )
    )

    main_chat_id = await _main_group_chat_id(db)
    escalated = []
    absent_skipped: list[dict] = []
    for lead in stale:
        if lead.user_id:
            absent_reason = await _operator_absent_reason(db, lead.user_id)
            if absent_reason:
                # Operator ishda ekanini davomat tasdiqlamagan — ayblab bo'lmaydi,
                # keyingi tick'da (check-in qilgach) qayta baholanadi.
                absent_skipped.append({"crm_lead_id": lead.crm_lead_id, "reason": absent_reason})
                continue

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
            if main_chat_id:
                await send_message(main_chat_id, text)
            lead.escalated_at = datetime.utcnow()
        escalated.append(entry)

    if escalated and not dry_run:
        await db.commit()
    return {"escalated": len(escalated), "absent_skipped": absent_skipped, "results": escalated}


async def send_corrections(db: AsyncSession, dry_run: bool) -> dict:
    """Avval eskalatsiya qilingan, keyin qo'ng'iroq TOPILGAN yoki QONUNIY sabab
    bilan yopilgan lidlar uchun guruhga tuzatuvchi xabar. Bu — 2-bug'ning
    aynan o'zi ("lid o'z vaqtida olingan edi, lekin kechikdi deb chiqdi")ga
    to'g'ridan-to'g'ri javob: yolg'on signal endi jim qolib ketmaydi, o'zi
    tuzatiladi."""
    pending = list(
        await db.scalars(
            select(HotLead).where(
                HotLead.escalated_at.isnot(None),
                HotLead.correction_sent_at.is_(None),
                HotLead.status.in_(("called", "resolved_no_call")),
            )
        )
    )
    if not pending:
        return {"sent": 0}

    # NOTIFY_BACKLOG_THRESHOLD izohiga qarang: bu funksiya birinchi marta
    # ishga tushganda, tizim eski (kunlar oldingi) yopilgan-lekin-tuzatilmagan
    # lidlarni ko'rishi mumkin — ularning barchasi haqida guruhga xabar
    # yuborish spam bo'ladi. Katta backlog bo'lsa — holat jimgina belgilanadi.
    is_backlog = len(pending) > NOTIFY_BACKLOG_THRESHOLD
    main_chat_id = await _main_group_chat_id(db)

    sent = []
    for lead in pending:
        if lead.status == "called":
            speed_min = round((lead.first_call_sec or 0) / 60, 1)
            text = (
                "✅ <b>Tuzatish — issiq lid aslida javobsiz qolmagan</b>\n"
                f"👤 {_lead_label(lead)} — qo'ng'iroq CRM'da topildi ({speed_min} daqiqada), "
                "eskalatsiya paytida hali ko'rinmagan edi."
            )
        else:
            text = (
                "ℹ️ <b>Tuzatish — issiq lid qonuniy sabab bilan yopilgan</b>\n"
                f"👤 {_lead_label(lead)} — bosqich: «{lead.resolved_reason}». "
                "Qo'ng'iroq kerak emas edi, avvalgi ogohlantirish ortiqcha edi."
            )
        entry = {"crm_lead_id": lead.crm_lead_id, "status": lead.status}
        if not dry_run:
            if not is_backlog and main_chat_id:
                await send_message(main_chat_id, text)
            lead.correction_sent_at = datetime.utcnow()
        sent.append(entry)

    if sent and not dry_run:
        await db.commit()
    return {"sent": len(sent), "backlog": is_backlog, "results": sent}


async def daily_accuracy_report(db: AsyncSession, day: date) -> dict:
    """Kunlik issiq-lid aniqlik hisoboti — "lid kechikkan yoki kechikmaganini
    aniqlash" degan nazorat talabiga javob. Xom signalga emas, kun yakuniga
    ishonish mumkin bo'lsin: shu kun YARATILGAN lidlar orasida — jami, hech
    eskalatsiyasiz vaqtida qo'ng'iroq qilingan, eskalatsiya qilingan-u keyin
    tasdiqlangan (yolg'on signal, avtomatik tuzatilgan), qonuniy sabab bilan
    yopilgan, va ESKALATSIYADAN KEYIN HAM hali ochiq qolgan (haqiqiy muammo)."""
    start_ts, end_ts = int(datetime.combine(day, datetime.min.time()).timestamp()), int(
        datetime.combine(day, datetime.max.time()).timestamp()
    )
    leads = list(
        await db.scalars(
            select(HotLead).where(HotLead.created_ts >= start_ts, HotLead.created_ts <= end_ts)
        )
    )
    leads = [l for l in leads if l.status != "baseline"]

    total = len(leads)
    escalated = [l for l in leads if l.escalated_at is not None]
    false_alarms = [l for l in escalated if l.status == "called"]
    legit_closed = [l for l in escalated if l.status == "resolved_no_call"]
    still_open = [l for l in escalated if l.status not in ("called", "resolved_no_call")]
    on_time = [l for l in leads if l.escalated_at is None and l.status == "called"]

    return {
        "date": day.isoformat(),
        "total": total,
        "on_time": len(on_time),
        "escalated": len(escalated),
        "escalated_false_alarm": len(false_alarms),
        "escalated_legit_closed": len(legit_closed),
        "escalated_still_open": len(still_open),
        "still_open_leads": [
            {"crm_lead_id": l.crm_lead_id, "contact": _lead_label(l)} for l in still_open
        ],
    }


async def tick(db: AsyncSession, dry_run: bool = False) -> dict:
    """Bitta to'liq aylanish: aniqlash+xabar → CRM holat sinxroni (drift/terminal)
    → birinchi qo'ng'iroq → eskalatsiya → tuzatish. dry_run — hech narsa
    yozmaydi/yubormaydi, faqat nima bo'lishini qaytaradi."""
    detect = await detect_and_notify(db, dry_run)
    sync = await sync_crm_state(db, dry_run)
    first_calls = await check_first_calls(db, dry_run)
    escalation = await escalate_stale(db, dry_run)
    corrections = await send_corrections(db, dry_run)
    return {
        "dry_run": dry_run,
        "detect": detect,
        "sync": sync,
        "first_calls": first_calls,
        "escalation": escalation,
        "corrections": corrections,
    }
