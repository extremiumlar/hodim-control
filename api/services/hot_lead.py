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
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import settings
from api.notify import notify_user
from api.services.push import Category
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
# 2026-08-06 (egasining talabi): "sovish" muddati endi QATTIQ KODLANMAGAN —
# HR o'z panelidan belgilaydi (`FinePolicy.hot_lead_cool_minutes`), boshlang'ich
# qiymat 10 daqiqa. Yuqoridagi ESCALATE_AFTER_MINUTES faqat ZAXIRA (sozlama
# umuman topilmasa) va eski matnlar uchun qoldi.
DEFAULT_COOL_MINUTES = 10
# Operatorga shaxsiy ogohlantirish bosqichlari (daqiqa). Egasining talabi:
# lid tushishi bilan xabar, keyin 3/5/7/9-daqiqada BOSHLIQ OHANGIDA (senlab)
# eslatma. Sovish muddati kichikroq sozlansa — undan katta bosqichlar
# o'tkazib yuboriladi.
REMINDER_STEPS = (3, 5, 7, 9)
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
# QAYTA tekshirish lid yoshiga qarab siyraklashadi (2026-08-03, CRM so'rov
# byudjeti): eskalatsiya oynasidagi yangi lid har tick tekshiriladi —
# speed-to-lead o'lchovi va 5-daqiqalik eskalatsiya aniq qolsin; javobsiz
# qolgan eski lidni esa 72 soat davomida har 2 daqiqada qayta so'rash CRM
# byudjetini behuda yer edi (10 lid × 3 raqamgacha = 30 so'rov/tick). Har
# qator: (lid yoshi shu chegaragacha, oxirgi tekshiruvdan keyin kutish).
FIRST_CALL_RECHECK_SCHEDULE = [
    (timedelta(minutes=30), timedelta(0)),  # yangi lid — har tick
    (timedelta(hours=3), timedelta(minutes=10)),
    (timedelta(hours=24), timedelta(minutes=30)),
]
FIRST_CALL_RECHECK_MAX_INTERVAL = timedelta(minutes=60)  # 24 soatdan eski lidlar
# Qo'ng'iroq lid yaratilishidan OLDIN ham bo'lishi mumkin: MOI_ZVONKI kabi
# manbalarda lid aynan qo'ng'iroqdan keyin avto-yaraladi (jonli misol: qo'ng'iroq
# liddan 27s oldin — 13547494). Shu oynadagi oldingi qo'ng'iroq ham "qabul"
# hisoblanadi (first_call_sec 0 ga qisqartiriladi), soxta eskalatsiya bo'lmaydi.
#
# 2026-08-06 (egasining aniq ko'rsatmasi): 10 daqiqa JUDA KICHIK edi. Amaldagi
# ish tartibi — operator mijoz bilan TO'LIQ gaplashib bo'lgach lidni CRM'ga
# kiritadi. Ya'ni qo'ng'iroq lid yaratilishidan 20-40 daqiqa OLDIN tugagan
# bo'lishi mumkin, va tizim buni "umuman qo'ng'iroq qilmadi" deb hisoblab,
# operator hali gaplashib turganda ogohlantirish yuborardi. Endi oyna 2 soat:
# shu oraliqda mijozning raqamiga aloqa bo'lgan bo'lsa — lid o'sha zahoti
# "aloqa qilingan" deb yopiladi, eslatma ham, sovutish e'loni ham bo'lmaydi.
PRE_CREATION_GRACE_SECONDS = 2 * 3600
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


async def hot_lead_rules(db: AsyncSession) -> tuple[int, float]:
    """(sovish_daqiqasi, jarima_summasi) — HR panelidan sozlanadigan qoida.

    Manba: GLOBAL `FinePolicy` qatori (kechikish jarimasi bilan bir joyda —
    HR uchun bitta sozlamalar sahifasi, `PayrollSettings`). Sozlanmagan
    bo'lsa boshlang'ich: 10 daqiqa / 0 so'm (egasining ko'rsatmasi — jarima
    HR belgilagunicha 0 turadi va xabarda summa yozilmaydi)."""
    from db.models import FinePolicy  # kech import — modul yuklanish tsikli

    policy = await db.scalar(
        select(FinePolicy).where(FinePolicy.scope == "global", FinePolicy.is_active.is_(True))
    )
    minutes = DEFAULT_COOL_MINUTES
    fine = 0.0
    if policy is not None:
        if policy.hot_lead_cool_minutes:
            minutes = int(policy.hot_lead_cool_minutes)
        if policy.hot_lead_fine:
            fine = float(policy.hot_lead_fine)
    return max(1, minutes), max(0.0, fine)


def _fmt_money(amount: float) -> str:
    """bot/handlers/payroll.py `_fmt_money` bilan bir xil ko'rinish."""
    return f"{int(round(amount)):,}".replace(",", " ") + " so'm"


def _notify_text(lead: HotLead, cool_minutes: int, fine: float) -> str:
    lines = ["🔥 <b>Yangi issiq lid — SENGA biriktirildi!</b>"]
    if lead.contact_name:
        lines.append(f"👤 {lead.contact_name}")
    if lead.phone:
        lines.append(f"📞 {lead.phone}")
    if lead.source:
        lines.append(f"🌐 Manba: {lead.source}")
    lines.append("")
    lines.append(
        f"⏱ <b>{cool_minutes} daqiqa</b> ichida qo'ng'iroq qil — keyin lid sovuydi. "
        "Qo'ng'iroq CRM'dan avtomatik tekshiriladi."
    )
    if fine > 0:
        lines.append(f"💸 Sovutsang ushlanma: <b>{_fmt_money(fine)}</b>.")
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


async def _pick_operator(db: AsyncSession) -> User | None:
    """Mas'ulsiz lidni kimga berish — BUGUN eng kam issiq lid olgan operator.

    Nomzodlar: `hot_lead_enabled` bayrog'i YOQILGAN faol xodimlar, ishdan
    chiqib ketmaganlari (`_operator_absent_reason`). Bayroq HR/Boshliq
    panelidan boshqariladi — ta'tildagi operator yoki sinov akkaunti
    (Tester) taqsimotdan bir bosishda chiqariladi va unga lid tushmaydi.
    Bu — CRM'da CRUD paydo bo'lgunicha vaqtinchalik taqsimlash qatlami; CRM
    tomonida mas'ul belgilansa, `sync_crm_state` uni baribir ustun deb oladi
    va yozuv o'sha odamga ko'chadi (bot taqsimoti CRM'ni buzmaydi)."""
    candidates = list(
        await db.scalars(
            select(User).where(User.is_active.is_(True), User.hot_lead_enabled.is_(True))
        )
    )
    if not candidates:
        return None

    today_start = datetime.utcnow() - timedelta(hours=24)
    counts = dict(
        (
            await db.execute(
                select(HotLead.user_id, func.count(HotLead.id))
                .where(HotLead.user_id.isnot(None), HotLead.detected_at >= today_start)
                .group_by(HotLead.user_id)
            )
        ).all()
    )

    available: list[User] = []
    for u in candidates:
        if await _operator_absent_reason(db, u.id) is None:
            available.append(u)
    pool = available or candidates  # hammasi ketgan bo'lsa ham lid egasiz qolmasin
    # Teng bo'lsa — id bo'yicha barqaror tartib (navbat aylanib turadi).
    return min(pool, key=lambda u: (counts.get(u.id, 0), u.id))


async def _lead_states_by_id(db: AsyncSession, crm_lead_ids: list[int]) -> dict[int, CrmLeadState]:
    if not crm_lead_ids:
        return {}
    rows = await db.scalars(select(CrmLeadState).where(CrmLeadState.crm_lead_id.in_(crm_lead_ids)))
    return {r.crm_lead_id: r for r in rows}


async def _operator_absent_reason(db: AsyncSession, user_id: int) -> str | None:
    """Operator hozir ishda EMASLIGINI ANIQ TASDIQLOVCHI dalil bo'lsa sababini
    qaytaradi (yoki `None` — ishda deb hisoblanadi). MUHIM (2026-07-25 tuzatish):
    ilgari "check-in yozuvi yo'q" HAM "ishda emas" deb hisoblanardi — bu Face ID
    check-in tizimi amalda deyarli ishlatilmagani uchun (production'da bir necha
    kunda bitta yozuv ham yo'q) DEYARLI HAR DOIM eskalatsiyani bloklab qo'yardi.
    Endi faqat ANIQ dalil (kimdir uni ishdan chiqib ketgan deb qayd etgan —
    check_out_time bor) hisobga olinadi; check-in yozuvi umuman yo'qligi
    "noaniq" deb qabul qilinadi va operatorni AYBLAYDI (aks holda amalda hech
    qachon eskalatsiya bo'lmasdi — bu tizimning asosiy maqsadini yo'qqa
    chiqarardi)."""
    today = datetime.now(TASHKENT_TZ).date()
    att = await db.scalar(
        select(Attendance).where(Attendance.user_id == user_id, Attendance.date == today)
    )
    if att is not None and att.check_out_time is not None:
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
    # Sovish muddati va jarima — HR sozlamasidan (bir marta, sikldan tashqarida).
    cool_minutes, fine = await hot_lead_rules(db)

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
                        _notify_text(lead, cool_minutes, fine)
                        + "\n\n↪️ Bu lid sizga CRM'da o'tkazildi.",
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
    cool_minutes, fine = await hot_lead_rules(db)
    results = []
    for item in fresh:
        detail = await adapter.get_lead_detail(item["id"]) or {}
        responsible_id = detail.get("responsible_id") or item.get("responsible_id")
        user = users_by_crm.get(str(responsible_id)) if responsible_id is not None else None
        # CRM'da mas'ul yo'q (yoki bizda topilmadi) — 2026-08-06 dan boshlab
        # bot O'ZI taqsimlaydi (CRM'da CRUD paydo bo'lgunicha vaqtinchalik
        # qatlam): eng kam yuklangan faol operatorga biriktiriladi. Ilgari
        # bunday lid GURUHGA "kim oladi?" deb tashlanardi — egasi buni bekor
        # qildi (guruh yangi lidlar bilan to'lib ketardi).
        assigned_by_bot = False
        if user is None:
            user = await _pick_operator(db)
            assigned_by_bot = user is not None

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
            "assigned_by_bot": assigned_by_bot,
        }
        if not dry_run:
            db.add(lead)
            await db.flush()
            delivered = None
            if user and user.telegram_id:
                text = _notify_text(lead, cool_minutes, fine)
                if assigned_by_bot:
                    text += "\n\n📌 Bu lidni CRM'da mas'ul belgilanmagani uchun bot senga biriktirdi."
                # Sotuv signali — ilova faol bo'lsa ham Telegram QOLADI
                # (services/push.py: PERSONAL_CATEGORIES).
                res = await notify_user(
                    db, user, Category.SALES_SIGNALS, text, data={"path": "/me/lead-stats"},
                )
                delivered = res["telegram"] or res["push"]
            # Hech qanday operator topilmasa — GURUHGA YOZILMAYDI (egasining
            # qarori). Lid baribir yoziladi va sovish hisobi ishlaydi; sovutish
            # e'lonida "mas'ul topilmadi" deb ko'rinadi.
            lead.notified_at = datetime.utcnow()
            entry["delivered"] = bool(delivered)
        results.append(entry)

    if not dry_run:
        await db.commit()
    return {"new": len(results), "results": results}


def _first_call_recheck_due(lead: HotLead, now_dt: datetime) -> bool:
    """Bu lidni SHU tick'da qayta tekshirish kerakmi — yoshiga mos jadval
    bo'yicha. Hali umuman tekshirilmagan lid har doim navbatda (eskalatsiya
    `last_call_check_at`siz boshlanmaydi — kutib qolmasin)."""
    if lead.last_call_check_at is None:
        return True
    since_last = now_dt - lead.last_call_check_at
    age = now_dt - lead.detected_at
    for age_limit, interval in FIRST_CALL_RECHECK_SCHEDULE:
        if age <= age_limit:
            return since_last >= interval
    return since_last >= FIRST_CALL_RECHECK_MAX_INTERVAL


async def check_first_calls(db: AsyncSession, dry_run: bool) -> dict:
    adapter = _adapter()
    if adapter is None:
        return {"checked": 0}

    now_dt = datetime.utcnow()
    cutoff = now_dt - timedelta(hours=FIRST_CALL_GIVE_UP_HOURS)
    open_pending = list(
        await db.scalars(
            select(HotLead)
            .where(
                HotLead.status.in_(("notified", "claimed")),
                HotLead.first_call_at.is_(None),
                HotLead.phone.isnot(None),
                HotLead.detected_at >= cutoff,
            )
            .order_by(HotLead.detected_at)
        )
    )
    # Navbat tartibi: avval hali BIR MARTA ham tekshirilmaganlar (eskalatsiya
    # shunga bog'liq), keyin eng yangi lidlar (issiq — tezlik shu yerda muhim).
    # Ilgari "eng eskisi birinchi, limit 10" edi — javobsiz eski backlog yangi
    # lidlarning tekshiruvini ochlikda qoldira olardi.
    due = [l for l in open_pending if _first_call_recheck_due(l, now_dt)]
    due.sort(key=lambda l: (l.last_call_check_at is not None, -l.detected_at.timestamp()))
    pending = due[:FIRST_CALL_CHECKS_PER_TICK]

    found = []
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


def _reminder_text(step: int, cool_minutes: int, lead: HotLead, fine: float) -> str:
    """Operatorga shaxsiy ogohlantirish — egasining talabi bo'yicha BOSHLIQ
    ohangida, senlab. Har bosqichda bosim ortadi."""
    left = max(0, cool_minutes - step)
    who = _lead_label(lead)
    fine_part = f" Ushlanma: {_fmt_money(fine)}." if fine > 0 else ""
    if step <= 3:
        return (
            f"⏰ <b>{step} daqiqa bo'ldi</b> — «{who}» ga hali qo'ng'iroq qilmading.\n"
            f"Mijoz kutib turibdi. {left} daqiqa qoldi, tez bo'l."
        )
    if step <= 5:
        return (
            f"🔥 <b>{step} daqiqa!</b> «{who}» sovib boryapti.\n"
            f"Hoziroq telefon qil — {left} daqiqadan keyin ushlanma yozaman.{fine_part}"
        )
    if step <= 7:
        return (
            f"⚠️ <b>{step} daqiqa bo'ldi — oxirgi ogohlantirish!</b>\n"
            f"«{who}» ga qo'ng'iroq qilmasang, {left} daqiqadan keyin ushlanmaga tushasan "
            f"va guruhga chiqaraman.{fine_part}"
        )
    return (
        f"🚨 <b>{step} daqiqa! Atigi {left} daqiqa qoldi.</b>\n"
        f"«{who}» ga hoziroq qo'ng'iroq qil. Aks holda «lidni sovutdi» deb guruhga "
        f"ismingni yozib chiqaraman va ushlanma yozaman.{fine_part}"
    )


async def send_reminders(db: AsyncSession, dry_run: bool) -> dict:
    """Bosqichli shaxsiy eslatmalar (3/5/7/9-daqiqa) — egasining talabi.

    Guruhga HECH NARSA yuborilmaydi; bu faqat operatorning o'ziga bosim.
    Qo'ng'iroq topilgan (`first_call_at`) yoki qonuniy yopilgan lid tabiiy
    ravishda tushib qoladi — ya'ni mijoz bilan gaplashib bo'lgan operator
    eslatma OLMAYDI (2026-08-06 shikoyatining to'g'ridan-to'g'ri yechimi:
    qo'ng'iroq oynasi PRE_CREATION_GRACE_SECONDS bilan lid yaratilishidan
    OLDINGI suhbatni ham qamrab oladi)."""
    now_local = datetime.now(TASHKENT_TZ)
    if not (ESCALATE_HOUR_FROM <= now_local.hour < ESCALATE_HOUR_TO):
        return {"reminded": 0, "off_hours": True}

    cool_minutes, fine = await hot_lead_rules(db)
    steps = [s for s in REMINDER_STEPS if s < cool_minutes]
    if not steps:
        return {"reminded": 0}

    now_ts = int(time.time())
    open_leads = list(
        await db.scalars(
            select(HotLead).where(
                HotLead.status.in_(("notified", "claimed")),
                HotLead.first_call_at.is_(None),
                HotLead.escalated_at.is_(None),
                HotLead.user_id.isnot(None),
                HotLead.created_ts >= now_ts - cool_minutes * 60,
                HotLead.created_ts <= now_ts - steps[0] * 60,
            )
        )
    )

    sent = []
    for lead in open_leads:
        age_min = int((now_ts - lead.created_ts) // 60)
        due = [s for s in steps if s <= age_min and s > (lead.last_reminder_minute or 0)]
        if not due:
            continue
        step = due[-1]  # bir necha bosqich o'tib ketgan bo'lsa — eng oxirgisi
        operator = await db.get(User, lead.user_id)
        if operator is None or not operator.telegram_id:
            continue
        if await _operator_absent_reason(db, lead.user_id):
            continue  # ishdan ketgan odamni siqmaymiz
        if not dry_run:
            await notify_user(
                db,
                operator,
                Category.SALES_SIGNALS,
                _reminder_text(step, cool_minutes, lead, fine),
                data={"path": "/me/lead-stats"},
                force_telegram=True,
            )
            lead.last_reminder_minute = step
        sent.append({"crm_lead_id": lead.crm_lead_id, "step": step, "operator": operator.full_name})

    if sent and not dry_run:
        await db.commit()
    return {"reminded": len(sent), "results": sent}


async def escalate_stale(db: AsyncSession, dry_run: bool) -> dict:
    """Sovish muddati o'tgan lidlar — guruhga «sovutildi» e'loni + jarima.

    2026-08-06: muddat HR sozlamasidan (`hot_lead_cool_minutes`, boshlang'ich
    10 daqiqa), xabar matni «kechikdi» emas «SOVUTILDI» — chunki bu endi
    yakuniy hukm (tuzatuvchi xabar guruhga YUBORILMAYDI, egasining talabi:
    guruhda «kechikdi → kechikmagan ekan» deb bardoq bo'lmasin)."""
    now_local = datetime.now(TASHKENT_TZ)
    if not (ESCALATE_HOUR_FROM <= now_local.hour < ESCALATE_HOUR_TO):
        return {"escalated": 0, "off_hours": True}

    cool_minutes, fine = await hot_lead_rules(db)
    # Muddat lid CRM'da YARATILGAN paytdan sanaladi (created_ts) — first_call_sec
    # bilan bir xil boshlanish nuqtasi, "tizim kech aniqladi" degan yumshoqlik yo'q.
    threshold_ts = int(time.time()) - cool_minutes * 60
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
        who = operator.full_name.strip() if operator else "mas'ul topilmadi"
        fine_line = (
            f"💸 Ushlanma: <b>{_fmt_money(fine)}</b>"
            if fine > 0
            else "💸 Ushlanma: belgilanmagan (HR panelidan sozlanadi)"
        )
        text = (
            "❄️ <b>ISSIQ LID SOVUTILDI</b>\n"
            f"👤 {_lead_label(lead)} — {minutes} daqiqa qo'ng'iroqsiz qoldi "
            f"(limit {cool_minutes} daqiqa).\n"
            f"🙍 Mas'ul: <b>{who}</b>\n"
            f"{fine_line}"
        )
        entry = {
            "crm_lead_id": lead.crm_lead_id,
            "operator": who,
            "minutes": minutes,
            "fine": fine,
            "text": text,
        }
        if not dry_run:
            if main_chat_id:
                await send_message(main_chat_id, text)
            lead.escalated_at = datetime.utcnow()
            lead.fine_amount = fine
            # Operatorning o'ziga ham yakuniy xabar — guruhdan bilib qolmasin.
            if operator and operator.telegram_id:
                await notify_user(
                    db,
                    operator,
                    Category.SALES_SIGNALS,
                    f"❄️ «{_lead_label(lead)}» lidini sovutding — {minutes} daqiqa "
                    f"qo'ng'iroq qilmading. Guruhga chiqarildi."
                    + (f"\n💸 Ushlanma: <b>{_fmt_money(fine)}</b>." if fine > 0 else ""),
                    data={"path": "/me/lead-stats"},
                    force_telegram=True,
                )
        escalated.append(entry)

    if escalated and not dry_run:
        await db.commit()
    return {"escalated": len(escalated), "absent_skipped": absent_skipped, "results": escalated}


async def send_corrections(db: AsyncSession, dry_run: bool) -> dict:
    """Sovutish e'lonidan KEYIN qo'ng'iroq topilsa / lid qonuniy yopilsa —
    holatni tuzatadi.

    ⚠️ 2026-08-06 (egasining aniq talabi): tuzatuvchi xabar GURUHGA ENDI
    YUBORILMAYDI — «kechikdi → kechikmagan ekan» ketma-ketligi guruhda bardoq
    qilardi. Tuzatish endi ikki joyda qoladi: (1) OPERATORNING O'ZIGA shaxsiy
    xabar (nohaq ayblov jim qolmasin), (2) kunlik hisobot/statistika
    raqamlarida (`daily_accuracy_report`, `cooled_by_operator`) — u yerda
    sovutilgan deb sanalmaydi. Guruhda esa faqat YAKUNIY hukm ko'rinadi,
    shuning uchun sovutish e'loni endi qo'ng'iroq tekshiruvidan keyin
    (`last_call_check_at`) va 2 soatlik oldingi-qo'ng'iroq oynasi bilan
    chiqadi — yolg'on signal ehtimoli o'zi minimal."""
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

    sent = []
    for lead in pending:
        if lead.status == "called":
            speed_min = round((lead.first_call_sec or 0) / 60, 1)
            text = (
                "✅ <b>Tuzatildi — sen aslida qo'ng'iroq qilgan ekansan</b>\n"
                f"👤 {_lead_label(lead)} — qo'ng'iroq CRM'da topildi ({speed_min} daqiqada). "
                "Bu lid «sovutilgan» hisobidan chiqarildi, ushlanma qo'llanmaydi."
            )
        else:
            text = (
                "ℹ️ <b>Tuzatildi — bu lid qonuniy sabab bilan yopilgan</b>\n"
                f"👤 {_lead_label(lead)} — bosqich: «{lead.resolved_reason}». "
                "Qo'ng'iroq kerak emas edi, avvalgi ogohlantirish ortiqcha edi."
            )
        entry = {"crm_lead_id": lead.crm_lead_id, "status": lead.status}
        if not dry_run:
            # Guruhga EMAS — faqat operatorning o'ziga (yuqoridagi izoh).
            if not is_backlog and lead.user_id:
                operator = await db.get(User, lead.user_id)
                if operator and operator.telegram_id:
                    await notify_user(
                        db, operator, Category.SALES_SIGNALS, text,
                        data={"path": "/me/lead-stats"}, force_telegram=True,
                    )
            lead.correction_sent_at = datetime.utcnow()
            # Jarima bekor qilinadi — bu lid endi sovutilgan hisoblanmaydi.
            lead.fine_amount = None
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
    yozmaydi/yubormaydi, faqat nima bo'lishini qaytaradi.

    2026-08-01: webhook-only rejimda (crm_mode) ANIQLASH bosqichi bu yerda
    o'tkazib yuboriladi — yangi lid kelganda Uysot webhook'i `detect_and_notify`ni
    O'ZI turtadi (uysot_webhook._maybe_trigger_hot_lead), operator DM'ni 2 daqiqa
    kutmasdan ~1 sekundda oladi. Qolgan bosqichlar (birinchi qo'ng'iroq,
    eskalatsiya, tuzatish) VAQTGA va call-history'ga bog'liq — webhook ularni
    bera olmaydi, shuning uchun scheduler'da qoladi."""
    from api.services import crm_mode

    if dry_run or await crm_mode.lead_polling_active(db):
        detect = await detect_and_notify(db, dry_run)
    else:
        detect = {"skipped": "webhook_mode"}
    sync = await sync_crm_state(db, dry_run)
    first_calls = await check_first_calls(db, dry_run)
    # Eslatmalar qo'ng'iroq tekshiruvidan KEYIN — shu tick'da qo'ng'iroq
    # topilgan lidga eslatma yuborilib qolmasin.
    reminders = await send_reminders(db, dry_run)
    escalation = await escalate_stale(db, dry_run)
    corrections = await send_corrections(db, dry_run)
    return {
        "dry_run": dry_run,
        "detect": detect,
        "sync": sync,
        "first_calls": first_calls,
        "reminders": reminders,
        "escalation": escalation,
        "corrections": corrections,
    }


async def cooled_by_operator(db: AsyncSession, day: date) -> list[dict]:
    """Kunlik guruh statistikasi uchun: shu kuni KIM nechta issiq lidni
    sovutgan (egasining talabi 2026-08-06).

    Sanoq `escalated_at` (sovutish e'lon qilingan payt) bo'yicha — ya'ni
    aynan o'sha kuni e'lon qilinganlar. Keyinchalik tuzatilgan (qo'ng'iroq
    topilgan yoki qonuniy yopilgan) lidlar HISOBGA KIRMAYDI — `status`
    hamon javobsiz bo'lganlari sanaladi."""
    start_local = datetime.combine(day, datetime.min.time(), tzinfo=TASHKENT_TZ)
    end_local = start_local + timedelta(days=1)
    start_utc = start_local.astimezone(timezone.utc).replace(tzinfo=None)
    end_utc = end_local.astimezone(timezone.utc).replace(tzinfo=None)

    rows = list(
        await db.scalars(
            select(HotLead).where(
                HotLead.escalated_at.isnot(None),
                HotLead.escalated_at >= start_utc,
                HotLead.escalated_at < end_utc,
                HotLead.status.notin_(("called", "resolved_no_call")),
            )
        )
    )
    if not rows:
        return []

    by_user: dict[int | None, dict] = {}
    for lead in rows:
        item = by_user.setdefault(
            lead.user_id, {"user_id": lead.user_id, "full_name": None, "count": 0, "fine": 0.0}
        )
        item["count"] += 1
        item["fine"] += float(lead.fine_amount or 0)

    for uid, item in by_user.items():
        if uid is None:
            item["full_name"] = "mas'ul topilmadi"
            continue
        user = await db.get(User, uid)
        item["full_name"] = user.full_name.strip() if user else f"#{uid}"

    return sorted(by_user.values(), key=lambda x: -x["count"])
