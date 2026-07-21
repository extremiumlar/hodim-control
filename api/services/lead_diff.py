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
from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import settings
from api.timeutil import local_range_utc_naive
from crm import get_crm_adapter
from db.models import CrmLeadState, LeadEvent

logger = logging.getLogger(__name__)

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
    stage_events, responsible_events, dry_run}. CRM xatosida {"ok": False, ...}."""
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


async def daily_operator_breakdown(
    db: AsyncSession, day: date, visit_pipe_status_id: int | None
) -> dict[int, dict]:
    """Kunlik operator kesimi — `LeadEvent`dan (taxminiy `updatedTimestamp`
    emas, haqiqiy voqealardan). Qaytaradi: {responsible_id: {name,
    leads_touched, visits}}.

    `leads_touched` — shu operatorga (voqea paytidagi `to_responsible_id`)
    tegishli HAQIQIY bosqich/mas'ul o'zgarish (yoki yangi lid) voqealari soni.
    `visits` — shu voqealardan aynan `visit_pipe_status_id`ga YANGI kirganlari
    (boshqa bosqichdan yoki yangi lid sifatida — allaqachon shu bosqichda
    bo'lgan-u boshqa narsasi o'zgargan lid ikkinchi marta sanalmaydi)."""
    day_start, day_end = local_range_utc_naive(day, day)
    rows = await db.scalars(
        select(LeadEvent).where(LeadEvent.detected_at >= day_start, LeadEvent.detected_at < day_end)
    )

    agg: dict[int, dict] = {}
    for ev in rows:
        rid = ev.to_responsible_id
        if rid is None:
            continue
        a = agg.setdefault(rid, {"name": ev.to_responsible_name or str(rid), "leads_touched": 0, "visits": 0})
        a["leads_touched"] += 1
        if (
            visit_pipe_status_id is not None
            and ev.to_pipe_status_id == visit_pipe_status_id
            and ev.from_pipe_status_id != visit_pipe_status_id
        ):
            a["visits"] += 1
    return agg


async def last_diff_tick_at(db: AsyncSession) -> datetime | None:
    """Diff-engine oxirgi marta qachon muvaffaqiyatli ishlagani — har skanerlashda
    HAR bir ko'rilgan lidning `last_seen_at`i yangilanadi (o'zgarishsiz bo'lsa
    ham), shuning uchun bu ma'lumot yangiligini ko'rsatadi (guruh digestida)."""
    return await db.scalar(select(func.max(CrmLeadState.last_seen_at)))
