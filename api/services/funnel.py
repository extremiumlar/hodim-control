"""Sotuv voronkasi va konversiyalar — o'lchov qatlami (1-bosqich).

Reja: `VORONKA_TARGET_REJASI.html` · Ta'riflar: `VORONKA_TARIFLAR.md`
(ta'riflar hujjati YAGONA haqiqat manbai — o'zgarsa shu modul ham o'zgaradi).

NEGA YANGI CRM SO'ROVI YO'Q: voronka butunlay MAVJUD jurnaldan quriladi —
`LeadEvent` (bosqich o'tishlari), `CrmLeadState` (lid va uning CRM'da
yaratilgan vaqti), `HourlyActual` (qo'ng'iroqlar). Uysot API'siga bitta ham
so'rov ketmaydi, ya'ni so'rov byudjetiga (60/daqiqa) ta'sir qilmaydi.

IKKI REJIM, IKKI SAVOL:
- `period`  — «shu davr ichida nechta tashrif bo'ldi» (operativ nazorat)
- `cohort`  — «shu davrda KELGAN lidlarning nechtasi keyin sotuvga aylandi»
  (haqiqiy konversiya). Vaqt siljishi tuzog'iga yagona to'g'ri javob:
  avgustda kelgan lid oktyabrda shartnoma qilishi mumkin.

«KAMIDA SHU BOSQICHGA YETGAN» QOIDASI: lid oraliq bosqichni chetlab o'tishi
mumkin (taklifsiz to'g'ridan tashrifga). Shuning uchun bosqich soni «aynan
shu bosqichga kirganlar» emas, «shu bosqich YOKI undan keyingisiga
yetganlar» deb hisoblanadi — aks holda konversiya 100% dan oshib ketardi.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.timeutil import local_range_utc_naive
from crm.config import (
    CRM_UYSOT_CONTRACT_PIPE_STATUS_IDS,
    CRM_UYSOT_INVITE_PIPE_STATUS_IDS,
    CRM_UYSOT_VISIT_PIPE_STATUS_IDS,
)
from db.models import CrmLeadState, HourlyActual, LeadEvent

# Bosqich tartibi (rank) — «kamida shu bosqichga yetgan» mantig'i shunga
# tayanadi. Qo'ng'iroq bosqichlari (urinish/suhbat) bu zanjirda YO'Q: ular
# lid kesimida emas, operator kesimida o'lchanadi (call-history lidga
# bog'lanmaydi) — voronkada alohida ko'rsatiladi.
STAGE_INVITE = "invite"
STAGE_VISIT = "visit"
STAGE_CONTRACT = "contract"

_STAGE_RANK = {STAGE_INVITE: 1, STAGE_VISIT: 2, STAGE_CONTRACT: 3}

STAGE_LABELS = {
    "lead": "Lid",
    "call_try": "Urinish (qo'ng'iroq)",
    "call_talk": "Suhbat (javob berilgan)",
    STAGE_INVITE: "Ofisga taklif",
    STAGE_VISIT: "Tashrif",
    STAGE_CONTRACT: "Shartnoma (uy)",
}

# Kogorta «pishishi» uchun taxminiy muddat — shundan yosh kogortaning
# konversiyasi «hali to'liq emas» deb belgilanadi (aks holda joriy oy har
# doim eng yomon ko'rinadi). 30 kun: lid kelib shartnomaga yetishi uchun
# real tsikl (kerak bo'lsa o'lchangach aniqlashtiriladi).
COHORT_MATURITY_DAYS = 30


def _stage_ids(stage: str) -> set[int]:
    if stage == STAGE_INVITE:
        return set(CRM_UYSOT_INVITE_PIPE_STATUS_IDS)
    if stage == STAGE_VISIT:
        return set(CRM_UYSOT_VISIT_PIPE_STATUS_IDS)
    return set(CRM_UYSOT_CONTRACT_PIPE_STATUS_IDS)


def _ids_at_or_after(stage: str) -> set[int]:
    """«Kamida shu bosqich» — shu va undan keyingi barcha bosqich ID'lari."""
    rank = _STAGE_RANK[stage]
    out: set[int] = set()
    for name, r in _STAGE_RANK.items():
        if r >= rank:
            out |= _stage_ids(name)
    return out


def _pct(numerator: int, denominator: int) -> float | None:
    """Konversiya foizi. Maxraj 0 bo'lsa `None` — «hisoblab bo'lmaydi»
    degani, 0% EMAS (bu ikkisi butunlay boshqa xabar)."""
    if not denominator:
        return None
    return round(numerator * 100 / denominator, 1)


async def _lead_ids_reached(
    db: AsyncSession, stage: str, start_utc: datetime, end_utc: datetime
) -> set[int]:
    """Berilgan oynada shu bosqichga (yoki undan keyingisiga) PASTDAN KIRGAN
    noyob lidlar.

    IKKI SHART, IKKALASI HAM ZARUR:
    1. `first_seen` chiqarib tashlanadi — u CRM hodisasi emas, skaner lidni
       birinchi ko'rgani (`lead_diff._is_visit_event` bilan bir xil qoida).
    2. `from` ALLAQACHON shu darajada bo'lmasin. Aks holda tashrifda turgan
       lid shartnomaga o'tganda «tashrif» qatorida QAYTA sanalardi — jonli
       tekshiruvda (2026-08) shu sabab 139 ta tashrif chiqdi, KPI esa ~46 ta
       ko'rsatardi. Bir xil hodisa ikki joyda ikki xil son bermasligi kerak."""
    ids = _ids_at_or_after(stage)
    if not ids:
        return set()
    rows = await db.scalars(
        select(LeadEvent.crm_lead_id)
        .where(
            LeadEvent.event_type != "first_seen",
            LeadEvent.to_pipe_status_id.in_(ids),
            LeadEvent.from_pipe_status_id.notin_(ids)
            | LeadEvent.from_pipe_status_id.is_(None),
            LeadEvent.detected_at >= start_utc,
            LeadEvent.detected_at < end_utc,
        )
        .distinct()
    )
    return set(rows)


async def _lead_ids_ever_reached(db: AsyncSession, stage: str, lead_ids: set[int]) -> set[int]:
    """Berilgan lidlardan qaysilari shu bosqichga QACHONDIR yetgan (kogorta
    uchun — vaqt chegarasi YO'Q, aynan shu vaqt siljishini hal qiladi)."""
    ids = _ids_at_or_after(stage)
    if not ids or not lead_ids:
        return set()
    rows = await db.scalars(
        select(LeadEvent.crm_lead_id)
        .where(
            LeadEvent.event_type != "first_seen",
            LeadEvent.to_pipe_status_id.in_(ids),
            LeadEvent.crm_lead_id.in_(lead_ids),
        )
        .distinct()
    )
    return set(rows)


async def _calls(db: AsyncSession, day_from: date, day_to: date) -> dict:
    """Urinish va suhbat — `HourlyActual` dan (u `missed` bo'yicha ajratadi).
    Bu yagona joy: `OperatorCallsDaily` da javob berilgan/berilmagan farqi
    saqlanmaydi, faqat kiruvchi/chiquvchi."""
    row = (
        await db.execute(
            select(
                func.coalesce(func.sum(HourlyActual.calls), 0),
                func.coalesce(func.sum(HourlyActual.answered), 0),
                func.coalesce(func.sum(HourlyActual.short_calls), 0),
                func.coalesce(func.sum(HourlyActual.talk_sec), 0),
            ).where(HourlyActual.date >= day_from, HourlyActual.date <= day_to)
        )
    ).first()
    calls, answered, short_calls, talk_sec = (int(v or 0) for v in (row or (0, 0, 0, 0)))
    return {
        "calls": calls,
        "answered": answered,
        "short_calls": short_calls,
        "talk_sec": talk_sec,
    }


def _epoch(dt_naive_utc: datetime) -> int:
    """UTC naive `datetime` -> unix sekund (`crm_created_ts` bilan bir o'lchov)."""
    return int(dt_naive_utc.replace(tzinfo=timezone.utc).timestamp())


async def _cohort_lead_ids(
    db: AsyncSession, start_utc: datetime, end_utc: datetime
) -> tuple[set[int], int]:
    """Shu oynada CRM'DA YARATILGAN lidlar + ulardan nechtasining yaratilish
    vaqti noma'lum. `crm_created_ts` NULL bo'lgan eski qatorlarda `first_seen_at`
    (skaner ko'rgan vaqt) ishlatiladi va ular «taxminiy» deb sanaladi.

    NEGA FILTR PYTHONDA: ikkita ustundan biri unix-sekund, ikkinchisi
    `DateTime` — ularni bitta SQL ifodasida solishtirish dialektga bog'liq
    bo'lib qolardi (`strftime` vs `extract(epoch)`). Jadval kichik (bir necha
    ming lid), shuning uchun sodda va ikkala bazada bir xil ishlaydigan yo'l
    tanlandi."""
    start_epoch, end_epoch = _epoch(start_utc), _epoch(end_utc)
    rows = list(
        await db.execute(
            select(
                CrmLeadState.crm_lead_id,
                CrmLeadState.crm_created_ts,
                CrmLeadState.first_seen_at,
            )
        )
    )
    ids: set[int] = set()
    approx = 0
    for lead_id, created_ts, first_seen_at in rows:
        if created_ts is not None:
            ts = int(created_ts)
            is_approx = False
        elif first_seen_at is not None:
            ts = _epoch(first_seen_at)
            is_approx = True
        else:
            continue
        if start_epoch <= ts < end_epoch:
            ids.add(lead_id)
            approx += 1 if is_approx else 0
    return ids, approx


async def period_funnel(db: AsyncSession, day_from: date, day_to: date) -> dict:
    """DAVR KESIMI: shu oraliqda sodir bo'lgan hodisalar soni.

    Diqqat: bu yerdagi «konversiya» — ma'lumot uchun. Haqiqiy konversiya
    faqat kogortada (`cohort_funnel`), chunki bu yerda maxraj va surat
    turli lidlarga tegishli bo'lishi mumkin."""
    start_utc, end_utc = local_range_utc_naive(day_from, day_to)
    calls = await _calls(db, day_from, day_to)

    new_leads, approx = await _cohort_lead_ids(db, start_utc, end_utc)
    invite = await _lead_ids_reached(db, STAGE_INVITE, start_utc, end_utc)
    visit = await _lead_ids_reached(db, STAGE_VISIT, start_utc, end_utc)
    contract = await _lead_ids_reached(db, STAGE_CONTRACT, start_utc, end_utc)

    # ⚠️ QO'NG'IROQ QATORLARI LID ZANJIRIDAN TASHQARIDA. Qo'ng'iroq operator
    # kesimida o'lchanadi va lidga bog'lanmaydi: bitta lidga 5 marta qo'ng'iroq
    # qilinishi mumkin, ya'ni «qo'ng'iroq ÷ lid» konversiya EMAS (100% dan
    # bemalol oshadi). Shuning uchun `call_try` da konversiya YO'Q, `call_talk`
    # da esa bor — u haqiqiy nisbat: «ko'tarish foizi» (javob ÷ urinish).
    # Bosqich konversiyalari lid zanjiri ichida qoladi: lid → taklif → tashrif
    # → shartnoma.
    rows = [
        {"key": "lead", "label": STAGE_LABELS["lead"], "value": len(new_leads), "conv_from_prev": None},
        {"key": "call_try", "label": STAGE_LABELS["call_try"], "value": calls["calls"],
         "conv_from_prev": None, "outside_chain": True},
        {"key": "call_talk", "label": STAGE_LABELS["call_talk"], "value": calls["answered"],
         "conv_from_prev": _pct(calls["answered"], calls["calls"]),
         "conv_label": "ko'tarish foizi", "outside_chain": True},
        {"key": STAGE_INVITE, "label": STAGE_LABELS[STAGE_INVITE], "value": len(invite),
         "conv_from_prev": _pct(len(invite), len(new_leads))},
        {"key": STAGE_VISIT, "label": STAGE_LABELS[STAGE_VISIT], "value": len(visit),
         "conv_from_prev": _pct(len(visit), len(invite))},
        {"key": STAGE_CONTRACT, "label": STAGE_LABELS[STAGE_CONTRACT], "value": len(contract),
         "conv_from_prev": _pct(len(contract), len(visit))},
    ]
    return {
        "mode": "period",
        "date_from": day_from.isoformat(),
        "date_to": day_to.isoformat(),
        "rows": rows,
        "calls_quality": {
            "short_calls": calls["short_calls"],
            "talk_minutes": round(calls["talk_sec"] / 60),
        },
        "stages_configured": {
            STAGE_INVITE: bool(_stage_ids(STAGE_INVITE)),
            STAGE_VISIT: bool(_stage_ids(STAGE_VISIT)),
            STAGE_CONTRACT: bool(_stage_ids(STAGE_CONTRACT)),
        },
        "approx_leads": approx,
    }


async def cohort_funnel(db: AsyncSession, day_from: date, day_to: date) -> dict:
    """KOGORTA: shu oraliqda kelgan lidlar keyinchalik qayergacha yetgan.

    Konversiya foizlari MANA SHU YERDA haqiqiy: surat ham, maxraj ham AYNAN
    bir xil lidlar to'plamiga tegishli."""
    start_utc, end_utc = local_range_utc_naive(day_from, day_to)
    lead_ids, approx = await _cohort_lead_ids(db, start_utc, end_utc)

    invite = await _lead_ids_ever_reached(db, STAGE_INVITE, lead_ids)
    visit = await _lead_ids_ever_reached(db, STAGE_VISIT, lead_ids)
    contract = await _lead_ids_ever_reached(db, STAGE_CONTRACT, lead_ids)

    total = len(lead_ids)
    rows = [
        {"key": "lead", "label": STAGE_LABELS["lead"], "value": total,
         "conv_from_prev": None, "conv_from_lead": None},
        {"key": STAGE_INVITE, "label": STAGE_LABELS[STAGE_INVITE], "value": len(invite),
         "conv_from_prev": _pct(len(invite), total), "conv_from_lead": _pct(len(invite), total)},
        {"key": STAGE_VISIT, "label": STAGE_LABELS[STAGE_VISIT], "value": len(visit),
         "conv_from_prev": _pct(len(visit), len(invite)), "conv_from_lead": _pct(len(visit), total)},
        {"key": STAGE_CONTRACT, "label": STAGE_LABELS[STAGE_CONTRACT], "value": len(contract),
         "conv_from_prev": _pct(len(contract), len(visit)), "conv_from_lead": _pct(len(contract), total)},
    ]

    age_days = (date.today() - day_to).days
    return {
        "mode": "cohort",
        "date_from": day_from.isoformat(),
        "date_to": day_to.isoformat(),
        "rows": rows,
        "age_days": age_days,
        # Yosh kogorta hali «pishmagan»: lidlarning bir qismi shartnomaga
        # yetishga ulgurmagan, shuning uchun foiz PASTROQ ko'rinadi.
        "mature": age_days >= COHORT_MATURITY_DAYS,
        "maturity_days": COHORT_MATURITY_DAYS,
        "stages_configured": {
            STAGE_INVITE: bool(_stage_ids(STAGE_INVITE)),
            STAGE_VISIT: bool(_stage_ids(STAGE_VISIT)),
            STAGE_CONTRACT: bool(_stage_ids(STAGE_CONTRACT)),
        },
        "approx_leads": approx,
    }


def _lead_channels(tags: list | None, source: str | None, group_by: str) -> list[str]:
    """Lid qaysi kanal(lar)ga tegishli.

    ⚠️ BITTA LID BIR NECHTA TEGDA BO'LISHI MUMKIN (masalan «#telegram» va
    «#Webinar_15_aprel»). Shunda u HAR IKKALA qatorda sanaladi — bu ataylab:
    «webinar lidlari qanday aylandi» va «telegram lidlari qanday aylandi»
    degan savollarning ikkalasi ham to'g'ri javob olishi kerak. Ya'ni kanal
    kesimidagi yig'indi umumiy liddan KO'P bo'lishi mumkin va bu xato emas."""
    if group_by == "source":
        return [source] if source else ["(manba yo'q)"]
    values = [str(t) for t in (tags or []) if str(t).strip()]
    return values or ["(tegsiz)"]


async def channel_funnel(
    db: AsyncSession, day_from: date, day_to: date, group_by: str = "tag"
) -> dict:
    """KANAL KESIMIDAGI KOGORTA: qaysi kanal lidlari sotuvga aylanadi.

    Kogorta rejimida (davr kesimi emas): «shu oyda kelgan telegram lidlari
    keyin qayergacha yetdi» — byudjetni qayerga surishni aynan shu ko'rsatadi.
    """
    start_utc, end_utc = local_range_utc_naive(day_from, day_to)
    lead_ids, _approx = await _cohort_lead_ids(db, start_utc, end_utc)
    if not lead_ids:
        return {"group_by": group_by, "rows": [], "date_from": day_from.isoformat(),
                "date_to": day_to.isoformat()}

    rows = list(
        await db.execute(
            select(CrmLeadState.crm_lead_id, CrmLeadState.tags, CrmLeadState.source).where(
                CrmLeadState.crm_lead_id.in_(lead_ids)
            )
        )
    )
    by_channel: dict[str, set[int]] = {}
    for lead_id, tags, source in rows:
        for ch in _lead_channels(tags, source, group_by):
            by_channel.setdefault(ch, set()).add(lead_id)

    visit_ids = await _lead_ids_ever_reached(db, STAGE_VISIT, lead_ids)
    contract_ids = await _lead_ids_ever_reached(db, STAGE_CONTRACT, lead_ids)

    out = []
    for channel, ids in by_channel.items():
        leads = len(ids)
        visits = len(ids & visit_ids)
        contracts = len(ids & contract_ids)
        out.append(
            {
                "channel": channel,
                "leads": leads,
                "visits": visits,
                "contracts": contracts,
                "lead_to_visit": _pct(visits, leads),
                "lead_to_contract": _pct(contracts, leads),
                "visit_to_contract": _pct(contracts, visits),
            }
        )
    # Eng ko'p lid bergan kanal yuqorida — lekin qaror uchun konversiyaga
    # qaraladi, shuning uchun ikkalasi ham ko'rsatiladi.
    out.sort(key=lambda r: (-r["leads"], r["channel"]))
    return {
        "group_by": group_by,
        "date_from": day_from.isoformat(),
        "date_to": day_to.isoformat(),
        "rows": out,
        "note": "Bitta lid bir nechta tegda bo'lishi mumkin — yig'indi umumiy liddan ko'p chiqadi",
    }


def weakest_link(rows: list[dict]) -> dict | None:
    """Eng zaif bo'g'in — konversiyasi eng past o'tish. Rejalashtirishda
    «qayerni tuzatsak eng ko'p foyda» degan savolga javob.

    Maxraji 0 bo'lgan (hisoblab bo'lmaydigan) o'tishlar chetlab o'tiladi —
    aks holda «0%» eng zaif bo'lib chiqib, haqiqiy muammoni yashirardi.
    Zanjirdan tashqaridagi qatorlar (qo'ng'iroq ko'tarish foizi) ham
    hisobga olinmaydi: u bosqich o'tishi emas, sifat ko'rsatkichi."""
    candidates = [
        r
        for r in rows
        if r.get("conv_from_prev") is not None
        and r["key"] != "lead"
        and not r.get("outside_chain")
    ]
    if not candidates:
        return None
    worst = min(candidates, key=lambda r: r["conv_from_prev"])
    return {"key": worst["key"], "label": worst["label"], "conv": worst["conv_from_prev"]}


async def monthly_series(db: AsyncSession, months: int = 6) -> list[dict]:
    """Oxirgi N oy bo'yicha kogorta konversiyasi — bitta oyga ishonib
    qolmaslik uchun (reja: «konversiya o'rtachasi + tebranish»).

    Har oy uchun: lid soni, tashrif/shartnoma konversiyasi va kogorta
    yetilganmi. O'rtachani chaqiruvchi tomon hisoblaydi — u yerda
    «yetilmagan oyni qo'shmaslik» qoidasini qo'llash oson."""
    today = date.today()
    out: list[dict] = []
    year, month = today.year, today.month
    for _ in range(months):
        start = date(year, month, 1)
        end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
        last_day = end - timedelta(days=1)
        data = await cohort_funnel(db, start, min(last_day, today))
        by_key = {r["key"]: r for r in data["rows"]}
        out.append(
            {
                "period": f"{start:%Y-%m}",
                "leads": by_key["lead"]["value"],
                "visits": by_key[STAGE_VISIT]["value"],
                "contracts": by_key[STAGE_CONTRACT]["value"],
                "lead_to_visit": by_key[STAGE_VISIT]["conv_from_lead"],
                "lead_to_contract": by_key[STAGE_CONTRACT]["conv_from_lead"],
                "visit_to_contract": by_key[STAGE_CONTRACT]["conv_from_prev"],
                "mature": data["mature"],
            }
        )
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    return list(reversed(out))
