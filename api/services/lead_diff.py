"""Diff-engine — CRM lidlarining HAQIQIY holat o'zgarishlarini (`LeadEvent`)
o'zimiz qayta tiklaymiz, chunki Uysot ochiq API'sida bosqich-o'tish tarixi
(event log) yo'q, faqat joriy holat va `updatedTimestamp` (istalgan tahrir,
aniq emas).

G'oya: har lid uchun oxirgi ko'rgan holatimizni (`CrmLeadState`) saqlaymiz.
Har skanerlashda CRM'dan joriy holatni olib, shu xotira bilan solishtiramiz —
farq chiqsa (bosqich va/yoki mas'ul o'zgargan), bu HAQIQIY voqea sifatida
`LeadEvent`ga yoziladi. Kunlik statistika (guruh digesti) endi shu jurnaldan
hisoblanadi — "bugun tegilgan (istalgan tahrir)" taxminidan farqli, aniq
"qachon, qaysi bosqichdan qaysi bosqichga o'tdi" voqeasi.

Ikki chaqiruv rejimi bor:
  - `full=False` (tez-tez, masalan har 2-3 daqiqa) — faqat so'nggi
    `CRM_UYSOT_LEAD_DIFF_LOOKBACK_DAYS` kunda yaratilgan lidlar (kichik,
    tez skan) — deyarli real-vaqtli yangilanish.
  - `full=True` (kamdan-kam, masalan tunda bir marta) — BUTUN baza (sekin) —
    lookback oynasidan tashqarida qolgan eski-lekin-qayta-faollashgan
    lidlarni ushlab qoladigan xavfsizlik to'ri.

Birinchi ishga tushishda (`CrmLeadState` bo'sh) — BASELINE: joriy holat
jimgina yoziladi, voqea YARATILMAYDI (aks holda mavjud minglab lidning
barchasi "o'zgardi" deb hisoblanib spam/noto'g'ri statistika bo'lardi —
`hot_lead.py`dagi bir xil naqsh)."""
import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import settings
from api.timeutil import TASHKENT_TZ, local_range_utc_naive
from crm import get_crm_adapter
from crm.config import CRM_UYSOT_CONTRACT_PIPE_STATUS_IDS
from db.models import CrmLeadState, LeadEvent

logger = logging.getLogger(__name__)


def contract_pipe_status_ids() -> set[int]:
    """«Shartnoma qilindi» bosqich ID'lari — statistikaning BARCHA yuzalari
    (guruh digestlari, bot «Lidlar statistikasi», sayt paneli) shu YAGONA
    manbadan o'qiydi. Tashrifda uchta modulda uchta nusxa bor (tarixiy) va
    ular bir-biridan uzilib qolishi mumkin edi — yangi ko'rsatkich shu xatoni
    takrorlamasin.

    Bo'sh ro'yxat = funksiya o'chiq: hech qayerda 🤝 ko'rsatilmaydi."""
    return set(CRM_UYSOT_CONTRACT_PIPE_STATUS_IDS)

# Diff natijasi bilan bitta commit'ga sig'adigan xavfsiz chegara — undan katta
# bo'lsa ham ishlaydi, faqat xotira/vaqt jihatidan diagnostika uchun log qilinadi.
_LARGE_SCAN_WARN_THRESHOLD = 20000


def _adapter():
    adapter = get_crm_adapter(settings.crm_type)
    if adapter is None:
        return None
    if not hasattr(adapter, "get_active_leads_snapshot"):
        return None
    return adapter


async def _existing_state_map(db: AsyncSession, lead_ids: list[int]) -> dict[int, CrmLeadState]:
    if not lead_ids:
        return {}
    out: dict[int, CrmLeadState] = {}
    chunk_size = 500  # SQLite/Postgres IN(...) chegarasidan xavfsiz pastda
    for i in range(0, len(lead_ids), chunk_size):
        chunk = lead_ids[i : i + chunk_size]
        rows = await db.scalars(select(CrmLeadState).where(CrmLeadState.crm_lead_id.in_(chunk)))
        for r in rows:
            out[r.crm_lead_id] = r
    return out


async def diff_tick(db: AsyncSession, full: bool = False, dry_run: bool = False) -> dict:
    """Bitta diff aylanish. Qaytaradi: {ok, baseline, scanned, new_leads,
    stage_events, responsible_events, dry_run}. CRM xatosida {"ok": False, ...}.

    2026-08-01: webhook JONLI bo'lgandagina (crm_mode dalil tekshiruvi) skan
    o'tkazib yuboriladi — bosqich/mas'ul o'zgarishlarini Uysot webhook'i
    `uysot_webhook.apply_lead_record` orqali xuddi shu CrmLeadState/LeadEvent
    jadvallariga yozadi. Webhook jim bo'lsa polling o'zi davom etadi.
    dry_run bundan mustasno (qo'lda diagnostika)."""
    from api.services import crm_mode

    if not dry_run and not await crm_mode.lead_polling_active(db):
        return {"ok": True, "skipped": "webhook_mode", "full": full}

    adapter = _adapter()
    if adapter is None:
        return {"ok": False, "reason": "CRM sozlanmagan yoki diff-engine'ni qo'llab-quvvatlamaydi"}

    lookback_ts = None if full else adapter.default_diff_lookback_ts()
    records = await adapter.get_active_leads_snapshot(lookback_ts)
    if records is None:
        return {"ok": False, "reason": "CRM'dan lidlarni olib bo'lmadi"}

    if len(records) > _LARGE_SCAN_WARN_THRESHOLD:
        logger.warning("Diff-engine skani katta hajmda: %s lid (full=%s)", len(records), full)

    is_baseline = (await db.scalar(select(func.count()).select_from(CrmLeadState))) == 0

    lead_ids = [r["id"] for r in records]
    existing = await _existing_state_map(db, lead_ids)

    now = datetime.utcnow()
    new_events: list[LeadEvent] = []
    new_leads = 0
    stage_events = 0
    responsible_events = 0

    for r in records:
        lead_id = r["id"]
        status_id = r["pipe_status_id"]
        stage_name = r["stage_name"]
        resp_id = r.get("responsible_id")
        resp_name = r.get("responsible_name")
        updated_ts = r.get("updated_ts") or 0

        prev = existing.get(lead_id)

        if prev is None:
            first_responsible_id = resp_id
            if not is_baseline:
                new_leads += 1
                new_events.append(
                    LeadEvent(
                        crm_lead_id=lead_id,
                        event_type="first_seen",
                        from_pipe_status_id=None,
                        from_stage_name=None,
                        to_pipe_status_id=status_id,
                        to_stage_name=stage_name,
                        from_responsible_id=None,
                        to_responsible_id=resp_id,
                        to_responsible_name=resp_name,
                        first_responsible_id=first_responsible_id,
                        crm_updated_ts=updated_ts,
                        detected_at=now,
                    )
                )
            if not dry_run:
                db.add(
                    CrmLeadState(
                        crm_lead_id=lead_id,
                        pipe_status_id=status_id,
                        stage_name=stage_name,
                        responsible_id=resp_id,
                        responsible_name=resp_name,
                        first_responsible_id=first_responsible_id,
                        crm_updated_ts=updated_ts,
                        first_seen_at=now,
                        last_seen_at=now,
                    )
                )
            continue

        stage_changed = prev.pipe_status_id != status_id
        responsible_changed = prev.responsible_id != resp_id
        if not is_baseline and (stage_changed or responsible_changed):
            event_type = "stage_change" if stage_changed else "responsible_change"
            new_events.append(
                LeadEvent(
                    crm_lead_id=lead_id,
                    event_type=event_type,
                    from_pipe_status_id=prev.pipe_status_id,
                    from_stage_name=prev.stage_name,
                    to_pipe_status_id=status_id,
                    to_stage_name=stage_name,
                    from_responsible_id=prev.responsible_id,
                    to_responsible_id=resp_id,
                    to_responsible_name=resp_name,
                    first_responsible_id=prev.first_responsible_id or prev.responsible_id,
                    crm_updated_ts=updated_ts,
                    detected_at=now,
                )
            )
            if stage_changed:
                stage_events += 1
            if responsible_changed:
                responsible_events += 1

        if not dry_run:
            prev.pipe_status_id = status_id
            prev.stage_name = stage_name
            prev.responsible_id = resp_id
            prev.responsible_name = resp_name
            if prev.first_responsible_id is None:
                prev.first_responsible_id = resp_id
            prev.crm_updated_ts = updated_ts
            prev.last_seen_at = now

    if not dry_run:
        db.add_all(new_events)
        await db.commit()
    # dry_run: hech narsa db.add() qilinmagan/mutatsiya qilinmagan — sessiyaga tegilmaydi.

    return {
        "ok": True,
        "baseline": is_baseline,
        "full": full,
        "scanned": len(records),
        "new_leads": new_leads,
        "stage_events": stage_events,
        "responsible_events": responsible_events,
        "dry_run": dry_run,
        "sample_events": [
            {
                "crm_lead_id": e.crm_lead_id,
                "type": e.event_type,
                "from_stage": e.from_stage_name,
                "to_stage": e.to_stage_name,
                "from_responsible": e.from_responsible_id,
                "to_responsible": e.to_responsible_id,
            }
            for e in new_events[:20]
        ],
    }


# Kechikkan aniqlash uchun qidiruv oynasi: voqea CRM'da bir kuni bo'lib, bizga
# keyinroq ko'rinishi mumkin (skan uzilishi — 2026-08-01..02 da ~28 soat; tungi
# 03:30 to'liq skan 30+ kunlik lidlarni ertasiga topadi). 3 kun — ko'rilgan eng
# uzun kechikishdan katta zaxira.
_DETECTION_LAG_DAYS = 3


def _is_stage_entry_event(ev: LeadEvent, stage_ids: set[int]) -> bool:
    """Bu voqea kuzatilayotgan bosqichga HAQIQIY KIRISHmi — ya'ni lid boshqa
    bosqichdan `stage_ids`dan biriga KO'CHIRILGANmi. Tashrif uchun ham,
    «Shartnoma qilindi» uchun ham AYNAN BIR XIL qoida (2026-08-14: shartnoma
    hisobi qo'shilganda umumiylashtirildi — ikki xil hisob qoidasi bo'lsa
    guruhdagi va saytdagi raqamlar bir-biriga mos kelmay qolardi).

    ⚠️ `first_seen` ATAYLAB CHIQARIB TASHLANDI (2026-08-13, egasining qarori).
    `first_seen` — bu CRM'dagi hodisa EMAS, bu bizning skanerimiz lidni
    BIRINCHI MARTA ko'rgani. Lid o'sha paytda allaqachon «Tashrif» bosqichida
    turgan bo'lsa, tizim uni "hozir tashrifga o'tdi" deb yozardi. Jonli
    oqibatlar: 2026-07-22 (jurnal boshlangan kun) — bir kunda 149 ta soxta
    "tashrif"; 08-11 — Firuzabonu'ga 8 tashrif, aslida 2 ta ko'chirish, qolgan
    6 tasi u o'zi CRM'ga kiritib darhol «Tashrif» qo'ygan lidlar (manba
    EMPLOYEE). Egasi: bunday lidlar tashrif deb SANALMASIN — faqat bosqich
    o'tishi (`stage_change`) hisoblanadi.

    `responsible_change` ham hisoblanmaydi: unda bosqich o'zgarmaydi (mas'ul
    almashadi), ya'ni `from == to` bo'lib quyidagi shart o'zi rad etadi."""
    return (
        bool(stage_ids)
        and ev.event_type != "first_seen"
        and ev.to_pipe_status_id in stage_ids
        and ev.from_pipe_status_id not in stage_ids
    )


def _event_effective_utc(ev: LeadEvent) -> datetime:
    """Voqeaning HAQIQIY vaqti (naive UTC). CRM `updatedTimestamp`i bosqich
    o'tishining o'zida yangilanadi, ya'ni voqea vaqtiga `detected_at`dan ancha
    yaqin — skan kechiksa ham tashrif O'Z kuniga tushishi uchun shuni olamiz
    (isbot 2026-08-02: 10:46 dagi partiya voqealarining 5 tasi CRM bo'yicha
    08-01 ga tegishli edi). Qiymat yo'q/nosog'lom (0, kelajak) bo'lsa —
    `detected_at` qoladi."""
    ts = ev.crm_updated_ts or 0
    if ts > 10**12:  # millisekundda kelib qolgan bo'lsa
        ts //= 1000
    if ts > 0:
        eff = datetime.utcfromtimestamp(ts)
        # CRM vaqti aniqlashdan keyin bo'lolmaydi — kichik soat farqiga ruxsat
        if eff <= ev.detected_at + timedelta(minutes=5):
            return eff
    return ev.detected_at


async def daily_operator_breakdown(
    db: AsyncSession,
    day: date,
    visit_pipe_status_ids: set[int] | None,
    contract_pipe_status_ids: set[int] | None = None,
) -> tuple[dict[int, dict], int, int]:
    """Kunlik operator kesimi — `LeadEvent`dan (taxminiy `updatedTimestamp`
    emas, haqiqiy voqealardan). Qaytaradi: ({responsible_id: {name,
    leads_touched, visits, contracts}}, jami_noyob_tashrif, jami_shartnoma).

    `jami_noyob_tashrif` — shu kuni Tashrifga KIRGAN voqealar soni, dual-kreditsiz
    (tashkilot "Jami" qatori uchun; kreditlar yig'indisi bitta tashrifni ikki
    odamga yozgani uchun jami sifatida ishlatilsa raqam shishardi).

    `contracts` — lid «Shartnoma qilindi» bosqich(lar)iga kirgan voqealar
    (2026-08-14, egasining qarori): tashrifdan FARQLI o'laroq DUAL-KREDIT YO'Q —
    shartnoma faqat uni YOPGAN mas'ulga (`to_responsible_id`) yoziladi. Shu
    sababli operator yig'indisi `jami_shartnoma` ga teng (mas'ulsiz voqeadan
    boshqa holatda) va qo'shimcha "kreditlar" izohi kerak emas. Shartnoma
    bosqichlari sozlanmagan bo'lsa hamma joyda 0 qaytadi.

    Voqea KUNGA `_event_effective_utc` bo'yicha biriktiriladi (`detected_at`
    emas) — skan kechikkanda ham tashrif haqiqatda bo'lgan kuniga tushadi.

    `leads_touched` — shu operatorga (voqea paytidagi `to_responsible_id`)
    tegishli HAQIQIY bosqich/mas'ul o'zgarish (yoki yangi lid) voqealari soni.

    `visits` — DUAL-KREDIT (5-band): lid `visit_pipe_status_ids`dan biriga
    YANGI kirsa (boshqa bosqichdan yoki yangi lid sifatida — allaqachon shu
    bosqichda bo'lgan-u boshqa narsasi o'zgargan lid ikkinchi marta
    sanalmaydi), JORIY mas'ul (`to_responsible_id`, "yopgan"/"tashrifga
    o'tkazgan" odam) +1 oladi. Bundan tashqari, agar shu lidning ENG BIRINCHI
    ko'rilgan mas'uli (`first_responsible_id` — CrmLeadState'da doimiy
    saqlanadi, hech qachon almashtirilmaydi) HOZIRGI mas'uldan FARQ QILSA
    (ya'ni lid boshqa odamdan — masalan operatordan — o'tkazib olingan), O'SHA
    BIRINCHI mas'ul HAM +1 tashrif oladi (\"lidni olib kelgan\" krediti,
    to'g'ridan-to'g'ri o'zi yopganidan ALOHIDA). Agar bitta odam boshidan
    oxirigacha o'zi olib kelib o'zi yopgan bo'lsa (first_responsible_id ==
    to_responsible_id) — faqat BITTA kredit (ikki marta sanalmaydi).

    Production'da tasdiqlangan (2026-07-24): CRM'da operatordan managerga
    haqiqiy o'tkazish voqealari (`responsible_change`) mavjud va
    `first_responsible_id` buni to'g'ri saqlaydi — lekin kuzatuv oynasi hali
    qisqa bo'lgani uchun operator→manager→Tashrif to'liq zanjiri hali jonli
    misolda ko'rilmagan (mexanizm to'g'ri qurilgan, vaqt sinovi kerak)."""
    day_start, day_end = local_range_utc_naive(day, day)
    # Kechikib aniqlangan voqealar ham kirsin: detected_at oynasi oldinga kengaytirilib,
    # kunga tegishlilik keyin effective vaqt bilan filtrlansin. Effective vaqt
    # detected_at'dan keyin bo'lolmaydi, shuning uchun day_start'dan oldin
    # aniqlangan voqea bu kunga tegishli emas — orqaga kengaytirish shart emas.
    rows = await db.scalars(
        select(LeadEvent).where(
            LeadEvent.detected_at >= day_start,
            LeadEvent.detected_at < day_end + timedelta(days=_DETECTION_LAG_DAYS),
        )
    )
    visit_ids = visit_pipe_status_ids or set()
    contract_ids = contract_pipe_status_ids or set()

    def _bucket(rid: int, name: str | None) -> dict:
        return agg.setdefault(
            rid, {"name": name or str(rid), "leads_touched": 0, "visits": 0, "contracts": 0}
        )

    agg: dict[int, dict] = {}
    total_visits = 0
    total_contracts = 0
    for ev in rows:
        eff = _event_effective_utc(ev)
        if not (day_start <= eff < day_end):
            continue

        is_new_visit = _is_stage_entry_event(ev, visit_ids)
        if is_new_visit:
            # Mas'ulsiz voqea operator kesimiga tushmaydi, lekin tashkilot
            # jamida baribir haqiqiy tashrif — yo'qolmasin.
            total_visits += 1
        is_new_contract = _is_stage_entry_event(ev, contract_ids)
        if is_new_contract:
            total_contracts += 1

        rid = ev.to_responsible_id
        if rid is None:
            continue
        a = _bucket(rid, ev.to_responsible_name)
        a["leads_touched"] += 1
        if is_new_contract:
            # Shartnoma — faqat yopgan mas'ulga (dual-kredit YO'Q)
            a["contracts"] += 1

        if not is_new_visit:
            continue
        a["visits"] += 1
        if ev.first_responsible_id is not None and ev.first_responsible_id != rid:
            # "Olib kelgan" (asl) mas'ulga ALOHIDA kredit — ismi shu voqeada
            # yo'q (faqat JORIY mas'ul nomi saqlanadi), shuning uchun ID bilan
            # boshlanadi; chaqiruvchi tomonda (daily_digest) mavjud
            # User.crm_visit_external_id orqali haqiqiy ismga almashtiriladi
            # (boshqa "Boshqa operatorlar" holatlari bilan bir xil naqsh).
            _bucket(ev.first_responsible_id, None)["visits"] += 1
    return agg, total_visits, total_contracts


async def visit_stats_range(
    db: AsyncSession,
    day_from: date,
    day_to: date,
    visit_pipe_status_ids: set[int] | None,
    contract_pipe_status_ids: set[int] | None = None,
) -> dict:
    """[day_from..day_to] (mahalliy kunlar) uchun tashrif seriyasi — bitta o'qish:
    {
      "daily_unique":      {date: int},        # tashkilot: Tashrifga KIRGAN noyob voqealar
      "daily_by_operator": {date: {rid: int}}, # dual-kredit (digest qoidasi bilan bir xil)
      "days_with_events":  set[date],          # umuman voqea bo'lgan kunlar
      "daily_contracts":            {date: int},        # «Shartnoma qilindi»ga kirgan voqealar
      "daily_contracts_by_operator": {date: {rid: int}}, # faqat yopgan mas'ul (dual-kredit yo'q)
    }
    Shartnoma kalitlari `contract_pipe_status_ids` berilmasa bo'sh qaytadi —
    eski chaqiruvchilar (crm_sync, /daily-results/recalc-visits) o'zgarishsiz
    ishlayveradi.
    `days_with_events` fallback uchun: LeadEvent jurnali 2026-07-22 dan boshlangan —
    undan oldingi (yoki tizim o'chiq bo'lgan) kunlarda voqea yo'q, lekin bu "tashrif
    bo'lmagan" degani emas; chaqiruvchi bunday kunlar uchun eski snapshot hisobiga
    qaytishi kerak. Kun `_event_effective_utc` bo'yicha olinadi (digest bilan mos)."""
    range_start, _ = local_range_utc_naive(day_from, day_from)
    _, range_end = local_range_utc_naive(day_to, day_to)
    rows = await db.scalars(
        select(LeadEvent).where(
            LeadEvent.detected_at >= range_start,
            LeadEvent.detected_at < range_end + timedelta(days=_DETECTION_LAG_DAYS),
        )
    )
    visit_ids = visit_pipe_status_ids or set()
    contract_ids = contract_pipe_status_ids or set()

    daily_unique: dict[date, int] = {}
    daily_by_operator: dict[date, dict[int, int]] = {}
    daily_contracts: dict[date, int] = {}
    daily_contracts_by_operator: dict[date, dict[int, int]] = {}
    days_with_events: set[date] = set()
    for ev in rows:
        eff = _event_effective_utc(ev)
        if not (range_start <= eff < range_end):
            continue
        local_day = eff.replace(tzinfo=timezone.utc).astimezone(TASHKENT_TZ).date()
        days_with_events.add(local_day)
        rid = ev.to_responsible_id

        if _is_stage_entry_event(ev, contract_ids):
            daily_contracts[local_day] = daily_contracts.get(local_day, 0) + 1
            if rid is not None:
                c_ops = daily_contracts_by_operator.setdefault(local_day, {})
                c_ops[rid] = c_ops.get(rid, 0) + 1

        if not _is_stage_entry_event(ev, visit_ids):
            continue
        daily_unique[local_day] = daily_unique.get(local_day, 0) + 1
        if rid is None:
            continue
        ops = daily_by_operator.setdefault(local_day, {})
        ops[rid] = ops.get(rid, 0) + 1
        if ev.first_responsible_id is not None and ev.first_responsible_id != rid:
            ops[ev.first_responsible_id] = ops.get(ev.first_responsible_id, 0) + 1
    return {
        "daily_unique": daily_unique,
        "daily_by_operator": daily_by_operator,
        "days_with_events": days_with_events,
        "daily_contracts": daily_contracts,
        "daily_contracts_by_operator": daily_contracts_by_operator,
    }


async def last_diff_tick_at(db: AsyncSession) -> datetime | None:
    """Diff-engine oxirgi marta qachon muvaffaqiyatli ishlagani — har skanerlashda
    HAR bir ko'rilgan lidning `last_seen_at`i yangilanadi (o'zgarishsiz bo'lsa
    ham), shuning uchun bu ma'lumot yangiligini ko'rsatadi (guruh digestida)."""
    return await db.scalar(select(func.max(CrmLeadState.last_seen_at)))
