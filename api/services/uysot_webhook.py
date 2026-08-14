"""Uysot CRM webhook'ini qayta ishlash (2026-08-01 da Uysot tomonidan ochildi,
hozircha FAQAT lid eventlari yuboriladi).

Nima uchun bu polling'ni DARHOL almashtirmaydi: Uysot webhook payload formati
rasmiy hujjatlashtirilmagan, shuning uchun qatlam ikki bosqichda ishlaydi —

  1. XOM JURNAL (`CrmWebhookLog`): har kelgan so'rov o'zgarishsiz saqlanadi.
     Format shu jonli oqimdan o'rganiladi; parse xato bo'lsa keyin shu
     jurnaldan qayta o'ynatish mumkin. Diff-tick/reconcile polling'i XAVFSIZLIK
     TO'RI sifatida ishlayveradi (webhook yo'qolgan voqeani baribir topadi);
     webhook o'zini oqlagach scheduler oraliqlarini siyraklashtirish mumkin.

  2. BEST-EFFORT QO'LLASH: payload'dan lid yozuvi ajratib olinsa, xuddi
     diff-engine (`lead_diff.py`) topgandek `CrmLeadState` yangilanadi va
     `LeadEvent` yoziladi — statistika/digest KUTMASDAN yangilanadi. Lid biz
     uchun YANGI bo'lsa issiq-lid aniqlash (`hot_lead.detect_and_notify`)
     cooldown bilan darhol ishga tushadi — operator DM'ni 2-daqiqalik polling
     o'rniga ~1 sekundda oladi (webhook so'rovining o'zi kutmaydi — fon vazifa).

Parser ATAYIN yumshoq: Uysot API'sining ma'lum maydon nomlari (camelCase:
`pipeStatusId`, `responsibleById`, `createdTimestamp`...) va ehtimoliy
o'ramlar (`{"event": ..., "data": {...}}`, ro'yxat, `{"lead": ...}`) birga
sinaladi. Ajratib bo'lmagan payload xato EMAS — jurnalga yozilib, issiq-lid
aniqlash baribir turtiladi (yangi lid bo'lsa CRM'dan to'g'ri o'qiladi)."""
import json
import logging
import time
from datetime import datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.services import celebration
from db.base import async_session
from db.models import CrmLeadState, CrmWebhookLog, LeadEvent

logger = logging.getLogger(__name__)

# Jurnal saqlash muddati — format o'rganish/diagnostika uchun yetarli, jadval
# cheksiz o'smaydi (har fon-ishlovda eski qatorlar o'chiriladi).
RETENTION_DAYS = 30

# Issiq-lid aniqlashni webhook'dan turtish oralig'i: Uysot bir lid uchun bir
# nechta eventni ketma-ket yuborishi mumkin — har biriga CRM /lead/filter
# so'rovi ketmasin (rate limit 60/daqiqa, boshqa job'lar bilan bo'lishilgan).
HOT_LEAD_TRIGGER_COOLDOWN_SECONDS = 20
_last_hot_lead_trigger = 0.0

# Lid ID'si bilan birga kamida bittasi bo'lsa, dict lid yozuvi deb qaraladi
_LEADISH_KEYS = (
    "pipeStatusId", "pipe_status_id", "statusId", "pipeStatus",
    "responsibleById", "responsible_by_id", "responsibleBy",
    "createdTimestamp", "updatedTimestamp", "created_timestamp", "updated_timestamp",
)
# O'ram kalitlari — ichiga kirib lid izlanadi (chuqurlik chegarasi bilan)
_WRAPPER_KEYS = ("data", "lead", "leads", "events", "event", "entry", "payload", "body", "result", "items")
# Event turi ko'rsatkichi bo'lishi mumkin bo'lgan kalitlar (o'ram darajasida)
_EVENT_TYPE_KEYS = ("event", "eventType", "event_type", "type", "action", "name")


def _lead_id(d: dict):
    for key in ("id", "leadId", "lead_id"):
        value = d.get(key)
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
    return None


def _first(d: dict, *keys):
    for key in keys:
        if d.get(key) is not None:
            return d[key]
    return None


def _as_int(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.lstrip("-").isdigit():
        return int(value)
    return None


def _ts_seconds(value):
    """Unix vaqt — millisekundda kelsa sekundga keltiriladi."""
    ts = _as_int(value)
    if ts is None:
        return None
    if ts > 10**12:  # millisekund
        ts //= 1000
    return ts


def _looks_like_lead(d) -> bool:
    return isinstance(d, dict) and _lead_id(d) is not None and any(k in d for k in _LEADISH_KEYS)


def _collect_leads(node, out: list, hint: str | None = None, depth: int = 0) -> None:
    """Payload daraxtidan lid ko'rinishidagi dict'larni yig'adi (chuqurlik ≤ 4).
    `hint` — yuqoriroq o'ramdagi event-turi satri (masalan "lead.created")."""
    if depth > 4:
        return
    if isinstance(node, list):
        for item in node:
            _collect_leads(item, out, hint, depth + 1)
        return
    if not isinstance(node, dict):
        return
    if _looks_like_lead(node):
        out.append({"record": node, "hint": hint})
        return
    new_hint = hint
    for key in _EVENT_TYPE_KEYS:
        value = node.get(key)
        if isinstance(value, str):
            new_hint = value
            break
    for key in _WRAPPER_KEYS:
        if key in node:
            _collect_leads(node[key], out, new_hint, depth + 1)


def parse_lead_events(payload) -> list[dict]:
    """Payload'dan normallashtirilgan lid yozuvlari ro'yxati. Har element:
    {"lead_id", "pipe_status_id", "stage_name", "responsible_id",
    "responsible_name", "updated_ts", "hint"} — topilmagan maydonlar None."""
    found: list[dict] = []
    _collect_leads(payload, found)
    out: list[dict] = []
    for item in found:
        r = item["record"]
        pipe_status = r.get("pipeStatus") if isinstance(r.get("pipeStatus"), dict) else {}
        out.append(
            {
                "lead_id": _lead_id(r),
                "pipe_status_id": _as_int(
                    _first(r, "pipeStatusId", "pipe_status_id", "statusId") or pipe_status.get("id")
                ),
                # `statusName` — Uysot webhook'ining HAQIQIY maydoni (2026-08-11,
                # jonli payload: {"lead": {"statusId": 539, "statusName":
                # "Yangi aloqalar", ...}}). Ilgari ro'yxatda yo'q edi va bosqich
                # nomi `_stage_name_fallback` orqali taxminan tiklanardi.
                "stage_name": _first(
                    r, "pipeStatusName", "stageName", "stage_name", "statusName"
                ) or pipe_status.get("name"),
                "responsible_id": _as_int(_first(r, "responsibleById", "responsible_by_id", "responsibleId")),
                "responsible_name": _first(r, "responsibleBy", "responsibleByName", "responsible_name"),
                "updated_ts": _ts_seconds(
                    _first(r, "updatedTimestamp", "updated_timestamp", "updatedAt")
                ),
                "hint": item["hint"],
            }
        )
    return out


async def _stage_name_fallback(db: AsyncSession, pipe_status_id: int) -> str:
    """Webhook'da bosqich nomi kelmasa: shu bosqichni allaqachon ko'rgan
    holat yozuvidan qayta ishlatamiz (diff-engine CRM'dan olib yozgan) —
    hot yo'lda qo'shimcha CRM so'rovi qilmaslik uchun."""
    name = await db.scalar(
        select(CrmLeadState.stage_name)
        .where(CrmLeadState.pipe_status_id == pipe_status_id)
        .limit(1)
    )
    return name or f"Bosqich #{pipe_status_id}"


async def apply_lead_record(db: AsyncSession, rec: dict) -> str:
    """Bitta lid yozuvini diff-engine semantikasi bilan qo'llaydi.
    Qaytaradi: "first_seen" | "stage_change" | "responsible_change" |
    "unchanged" | "skipped" (maydon yetishmasa).

    `lead_diff.diff_tick` bilan bir xil qoidalar: baseline'gacha (CrmLeadState
    bo'sh) voqea yozilmaydi; o'zgarish bo'lsa LeadEvent + holat yangilanadi.
    MUHIM: bu funksiya commit QILMAYDI — chaqiruvchi tranzaksiyani yakunlaydi."""
    lead_id = rec.get("lead_id")
    status_id = rec.get("pipe_status_id")
    if lead_id is None or status_id is None:
        return "skipped"

    stage_name = rec.get("stage_name") or await _stage_name_fallback(db, status_id)
    resp_id = rec.get("responsible_id")
    resp_name = rec.get("responsible_name")
    updated_ts = rec.get("updated_ts") or int(time.time())
    now = datetime.utcnow()

    prev = await db.get(CrmLeadState, lead_id)
    if prev is None:
        # diff-engine hali umuman baseline qilmagan bo'lsa — voqea yozmaymiz
        # (lead_diff.py'dagi baseline qoidasi bilan bir xil sabab)
        is_baseline = (await db.scalar(select(func.count()).select_from(CrmLeadState))) == 0
        if not is_baseline:
            db.add(
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
                    first_responsible_id=resp_id,
                    crm_updated_ts=updated_ts,
                    detected_at=now,
                )
            )
        db.add(
            CrmLeadState(
                crm_lead_id=lead_id,
                pipe_status_id=status_id,
                stage_name=stage_name,
                responsible_id=resp_id,
                responsible_name=resp_name,
                first_responsible_id=resp_id,
                crm_updated_ts=updated_ts,
                first_seen_at=now,
                last_seen_at=now,
            )
        )
        return "first_seen"

    stage_changed = prev.pipe_status_id != status_id
    responsible_changed = prev.responsible_id != resp_id
    result = "unchanged"
    if stage_changed or responsible_changed:
        result = "stage_change" if stage_changed else "responsible_change"
        db.add(
            LeadEvent(
                crm_lead_id=lead_id,
                event_type=result,
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
    prev.pipe_status_id = status_id
    prev.stage_name = stage_name
    prev.responsible_id = resp_id
    prev.responsible_name = resp_name
    if prev.first_responsible_id is None:
        prev.first_responsible_id = resp_id
    prev.crm_updated_ts = updated_ts
    prev.last_seen_at = now
    return result


async def _maybe_trigger_hot_lead(db: AsyncSession) -> bool:
    """Issiq-lid aniqlashni (DM) darhol turtadi — cooldown va scheduler'dagi
    bilan BIR XIL yoqish shartlari (env + runtime toggle) bilan. Xato issiq-lid
    yo'lida qolsin — webhook qayta ishlashini yiqitmasin."""
    global _last_hot_lead_trigger
    now = time.monotonic()
    if now - _last_hot_lead_trigger < HOT_LEAD_TRIGGER_COOLDOWN_SECONDS:
        return False
    _last_hot_lead_trigger = now

    from api.config import settings
    from api.routers.ai_watch import _get_ai_config
    from api.services import hot_lead

    if not settings.hot_lead_enabled:
        return False
    cfg = await _get_ai_config(db)
    if not cfg.hot_leads_enabled:
        return False
    try:
        detect = await hot_lead.detect_and_notify(db, dry_run=False)
        if detect.get("new"):
            logger.info("Webhook turtkisi bilan %s ta yangi issiq lid yuborildi", detect["new"])
        return True
    except Exception:  # noqa: BLE001
        logger.exception("Webhook'dan issiq-lid aniqlashda xato")
        return False


async def process_log_entry(log_id: int) -> None:
    """Fon vazifa (javob 200 qaytgandan keyin): jurnal yozuvini parse qilib
    qo'llaydi. O'Z sessiyasini ochadi — request sessiyasi allaqachon yopilgan."""
    async with async_session() as db:
        entry = await db.get(CrmWebhookLog, log_id)
        if entry is None:
            return
        try:
            payload = json.loads(entry.payload)
        except ValueError:
            entry.note = "JSON emas"
            await db.commit()
            return

        records = parse_lead_events(payload)
        results: list[str] = []
        new_lead_seen = False
        for rec in records:
            outcome = await apply_lead_record(db, rec)
            results.append(outcome)
            if outcome == "first_seen":
                new_lead_seen = True

        entry.parsed_events = len([r for r in results if r != "skipped"])
        counts = {r: results.count(r) for r in set(results)}
        entry.note = ", ".join(f"{k}={v}" for k, v in sorted(counts.items())) or "lid topilmadi"
        # Eski jurnal qatorlarini shu yerda tozalaymiz (alohida job shart emas)
        await db.execute(
            delete(CrmWebhookLog).where(
                CrmWebhookLog.received_at < datetime.utcnow() - timedelta(days=RETENTION_DAYS)
            )
        )
        await db.commit()

        # Yangi lid ko'rinsa YOKI hech narsa ajratilmasa (format notanish —
        # yangi lid bo'lishi mumkin) issiq-lidni turtamiz: CRM'dan to'g'ri
        # o'qib, operatorga DM ~1 sekundda ketadi (2 daqiqalik polling o'rniga).
        if new_lead_seen or not records:
            await _maybe_trigger_hot_lead(db)

        # Tashrif/shartnoma tabrigi — voqealar yozilgandan KEYIN. Bu yerda
        # chaqirilgani uchun guruhga video CRM'dagi o'zgarishdan bir necha
        # soniyada boradi (cron zaxira bo'lib qoladi, u har daqiqada ishlaydi).
        # Xato tabrik yo'lida qolsin — webhook qayta ishlashini yiqitmasin.
        if any(r in {"stage_change", "responsible_change"} for r in results):
            try:
                await celebration.announce_pending(db)
            except Exception:  # noqa: BLE001
                logger.exception("Webhook'dan tabrik e'lon qilishda xato")
