"""Teskari kalkulyator — «10 uy» maqsadidan kerakli raqamlar (voronka 4-bosqich).

Reja: `VORONKA_TARGET_REJASI.html` 04-bosqich · Ta'riflar: `VORONKA_TARIFLAR.md`

HISOB PASTDAN YUQORIGA YURADI:
    shartnoma (maqsad)
      ÷ tashrif→shartnoma %  = kerakli TASHRIF
      ÷ taklif→tashrif %     = kerakli TAKLIF
      ÷ lid→taklif %         = kerakli LID
      × lid boshiga suhbat   = kerakli SUHBAT (undan urinish)
      × CPL                  = kerakli BYUDJET
      ÷ qamrov→lid %         = kerakli AUDITORIYA

NEGA REJA 1-BOSQICH EMAS, 4-BOSQICH BO'LGANI SHU YERDA KO'RINADI:
bo'lish amali oson, lekin uning YAGONA kirishi — konversiya foizlari. Ular
o'lchanmagan bo'lsa, kalkulyator ishonchli ko'rinishdagi O'YLAB TOPILGAN
raqamlarni chiqaradi. Shuning uchun bu modul har bir farazning QAYERDAN
kelganini (`measured` / `override` / `default`) ochiq qaytaradi va
o'lchanmagan bo'lsa buni yashirmaydi.

FARAZ MANBALARI (ustuvorlik tartibida):
  1. `override` — rahbar qo'lda kiritgan («keyingi oy 8% qilamiz»)
  2. `measured` — YETILGAN kogortalarning o'rtachasi (`funnel.monthly_series`)
  3. `default`  — hech qanday o'lchov bo'lmasa: zaxira qiymat, ATAYLAB
     «taxminiy» deb belgilanadi va rejaga ishonch past ekani aytiladi.
"""
from __future__ import annotations

import math
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.services import ad_spend as ad_spend_service
from api.services import funnel as funnel_service
from api.timeutil import local_range_utc_naive
from db.models import AdSpend, FunnelMonth, HourlyActual

# Hech qanday o'lchov bo'lmaganda ishlatiladigan zaxira farazlar. Ular
# «haqiqat» EMAS — shunchaki kalkulyator ishga tushishi uchun. Har biri
# javobda `source="default"` bilan belgilanadi.
DEFAULTS = {
    # ⚠️ Kalkulyator taklif bosqichini ALOHIDA ishlatmaydi: oylik qatorda u
    # o'lchanmaydi va lid→tashrif dan ajratib bo'lmaydi. Shuning uchun zaxira
    # qiymat ham BIRLASHTIRILGAN bo'lishi shart — ilgari bu yerda ikkita
    # alohida kalit turardi va `lead_to_visit` uchun zaxira UMUMAN yo'q edi,
    # ya'ni o'lchov bo'lmasa butun zanjir «hisoblanmadi» bo'lib qolardi.
    # 25% (taklif) × 30% (tashrif) ≈ 7.5%.
    "lead_to_visit": 7.5,        # lidning qanchasi ofisga kelib tashrif bo'ladi
    "visit_to_contract": 10.0,   # tashrifning qanchasi shartnoma bo'ladi
    "talks_per_lead": 1.5,       # bitta lidga o'rtacha nechta SUHBAT
    "pickup_rate": 45.0,         # urinishning qanchasi javob beriladi
    "cpl": None,                 # lid narxi — zaxira qiymat YO'Q (pul o'ylab topilmaydi)
    "reach_to_lead": None,       # qamrov→lid — zaxira qiymat YO'Q
}

# O'rtacha hisoblashda nechta oy qaraladi (yetilganlaridan).
BASELINE_MONTHS = 6

# Oy o'rtachaga kirishi uchun kamida shuncha lid bo'lishi kerak. NEGA:
# jonli tekshiruvda (2026-08-15) bir necha eski oyda 1-2 tadan lid bor edi
# (kogorta ustuni to'lib borayotgani sababli) va ularning tashrifi 0 —
# natijada «o'lchangan konversiya 0%» chiqib, butun hisob to'xtab qoldi.
# Kichik namuna o'lchov emas.
MIN_LEADS_FOR_BASELINE = 20


def _avg(values: list[float]) -> float | None:
    vals = [v for v in values if v is not None]
    return round(sum(vals) / len(vals), 2) if vals else None


async def _call_ratios(db: AsyncSession, months: int) -> tuple[float | None, float | None]:
    """(lid boshiga suhbat, ko'tarish foizi) — oxirgi N oy bo'yicha.

    Qo'ng'iroq lidga bog'lanmaydi (operator kesimida o'lchanadi), shuning
    uchun «lid boshiga suhbat» — jami suhbat ÷ jami lid nisbati, aniq
    biriktirish emas. Reja uchun shu yetarli: bizga «shuncha lid uchun
    operatorlar qancha gaplashishi kerak» degan MIQYOS kerak."""
    today = date.today()
    start = (today.replace(day=1) - timedelta(days=31 * months)).replace(day=1)
    start_utc, end_utc = local_range_utc_naive(start, today)

    row = (
        await db.execute(
            select(
                func.coalesce(func.sum(HourlyActual.calls), 0),
                func.coalesce(func.sum(HourlyActual.answered), 0),
            ).where(HourlyActual.date >= start, HourlyActual.date <= today)
        )
    ).first()
    calls, answered = int(row[0] or 0), int(row[1] or 0)

    lead_ids, _approx = await funnel_service._cohort_lead_ids(db, start_utc, end_utc)  # noqa: SLF001
    leads = len(lead_ids)

    talks_per_lead = round(answered / leads, 2) if leads and answered else None
    pickup = round(answered * 100 / calls, 1) if calls else None
    return talks_per_lead, pickup


async def _measured_cpl(db: AsyncSession, months: int) -> float | None:
    """O'lchangan CPL — xarajati kiritilgan oylarning jami xarajati ÷ jami lid.

    Oy bo'yicha o'rtacha OLINMAYDI: kichik oy katta oy bilan teng vaznga ega
    bo'lib qolardi. To'g'ri yo'l — umumiy nisbat."""
    today = date.today()
    year, month = today.year, today.month
    total_spend = 0.0
    total_leads = 0
    for _ in range(months):
        period = f"{year}-{month:02d}"
        has_spend = await db.scalar(select(AdSpend.id).where(AdSpend.period == period).limit(1))
        if has_spend is not None:
            eco = await ad_spend_service.economics(db, period)
            total_spend += eco["totals"]["spend"]
            total_leads += eco["totals"]["leads"]
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    return round(total_spend / total_leads, 1) if total_leads and total_spend else None


async def _measured_reach_to_lead(db: AsyncSession, months: int) -> float | None:
    """Qamrov→lid foizi — faqat qamrov kiritilgan xarajat qatorlaridan."""
    today = date.today()
    year, month = today.year, today.month
    reach_total = 0
    leads_total = 0
    for _ in range(months):
        period = f"{year}-{month:02d}"
        eco = await ad_spend_service.economics(db, period)
        for r in eco["rows"]:
            if r["reach"] and r["matched"]:
                reach_total += r["reach"]
                leads_total += r["leads"]
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    return round(leads_total * 100 / reach_total, 3) if reach_total and leads_total else None


async def baseline(db: AsyncSession, months: int = BASELINE_MONTHS) -> dict:
    """O'lchangan farazlar + ular qancha ishonchli ekani."""
    series = await funnel_service.monthly_series(db, months)
    mature = [
        m for m in series if m["mature"] and m["leads"] >= MIN_LEADS_FOR_BASELINE
    ]

    lead_to_visit = _avg([m["lead_to_visit"] for m in mature])
    visit_to_contract = _avg([m["visit_to_contract"] for m in mature])
    talks_per_lead, pickup = await _call_ratios(db, months)
    cpl = await _measured_cpl(db, months)
    reach_to_lead = await _measured_reach_to_lead(db, months)

    # Taklif bosqichi alohida o'lchanmagan (oylik qatorda yo'q) — uni
    # lid→tashrif dan ajratib bo'lmaydi, shuning uchun kalkulyator
    # ikkisini BITTA bo'g'in deb oladi: lid→tashrif.
    return {
        "months_used": len(mature),
        "values": {
            "lead_to_visit": lead_to_visit,
            "visit_to_contract": visit_to_contract,
            "talks_per_lead": talks_per_lead,
            "pickup_rate": pickup,
            "cpl": cpl,
            "reach_to_lead": reach_to_lead,
        },
        # Ishonch darajasi: nechta yetilgan oy asos bo'ldi. 0 — hech narsa
        # o'lchanmagan, reja butunlay taxminga quriladi.
        "confidence": "yo'q" if not mature else ("past" if len(mature) < 3 else "o'rta"),
    }


def _resolve(key: str, overrides: dict, measured: dict) -> tuple[float | None, str]:
    """Faraz qiymati va uning manbai.

    ⚠️ NOL O'LCHOV ISHLATILMAYDI: konversiya aynan 0 bo'lsa, u bo'linuvchi
    sifatida butun zanjirni to'xtatadi («0 ga bo'lish»). Amalda bu «bu oy
    hech kim sotmagan» degani emas, «bu oyda o'lchash uchun ma'lumot
    yetarli emas» degani — shuning uchun zaxira farazga o'tiladi va manba
    `default` deb ko'rsatiladi (foydalanuvchi buni ko'rib turadi)."""
    if overrides.get(key) is not None:
        return float(overrides[key]), "override"
    value = measured.get(key)
    if value is not None and float(value) > 0:
        return float(value), "measured"
    fallback = DEFAULTS.get(key)
    return (float(fallback), "default") if fallback is not None else (None, "yo'q")


def _up(value: float) -> int:
    """Yuqoriga yaxlitlash — «7,2 ta tashrif kerak» degani amalda 8 ta."""
    return int(math.ceil(value - 1e-9))


async def calculate(
    db: AsyncSession, period: str, target_contracts: int, overrides: dict | None = None
) -> dict:
    """Maqsaddan teskari hisob. `overrides` — rahbar qo'lda kiritgan farazlar."""
    overrides = {k: v for k, v in (overrides or {}).items() if v is not None}
    base = await baseline(db)
    measured = base["values"]

    lead_to_visit, src_ltv = _resolve("lead_to_visit", overrides, measured)
    visit_to_contract, src_vtc = _resolve("visit_to_contract", overrides, measured)
    talks_per_lead, src_tpl = _resolve("talks_per_lead", overrides, measured)
    pickup, src_pick = _resolve("pickup_rate", overrides, measured)
    cpl, src_cpl = _resolve("cpl", overrides, measured)
    reach_to_lead, src_reach = _resolve("reach_to_lead", overrides, measured)

    # Zanjir: shartnoma -> tashrif -> lid -> suhbat/urinish -> byudjet -> qamrov
    visits = target_contracts / (visit_to_contract / 100) if visit_to_contract else None
    leads = visits / (lead_to_visit / 100) if visits is not None and lead_to_visit else None
    talks = leads * talks_per_lead if leads is not None and talks_per_lead else None
    tries = talks / (pickup / 100) if talks is not None and pickup else None
    budget = leads * cpl if leads is not None and cpl else None
    reach = leads / (reach_to_lead / 100) if leads is not None and reach_to_lead else None

    chain = [
        {"key": "reach", "label": "Auditoriya (qamrov)", "value": _up(reach) if reach else None,
         "source": src_reach},
        {"key": "tries", "label": "Urinish (qo'ng'iroq)", "value": _up(tries) if tries else None,
         "source": src_pick},
        {"key": "talks", "label": "Suhbat (javob berilgan)", "value": _up(talks) if talks else None,
         "source": src_tpl},
        {"key": "leads", "label": "Lid", "value": _up(leads) if leads else None, "source": src_ltv},
        {"key": "visits", "label": "Tashrif", "value": _up(visits) if visits else None,
         "source": src_vtc},
        {"key": "contracts", "label": "Shartnoma (uy)", "value": target_contracts,
         "source": "maqsad"},
    ]

    assumptions = {
        "lead_to_visit": {"value": lead_to_visit, "source": src_ltv, "unit": "%"},
        "visit_to_contract": {"value": visit_to_contract, "source": src_vtc, "unit": "%"},
        "talks_per_lead": {"value": talks_per_lead, "source": src_tpl, "unit": "ta"},
        "pickup_rate": {"value": pickup, "source": src_pick, "unit": "%"},
        "cpl": {"value": cpl, "source": src_cpl, "unit": "so'm"},
        "reach_to_lead": {"value": reach_to_lead, "source": src_reach, "unit": "%"},
    }
    # Nima YETISHMAYAPTI — foydalanuvchi nimani kiritishi kerakligini bilsin
    missing = [k for k, v in assumptions.items() if v["value"] is None]

    return {
        "period": period,
        "target_contracts": target_contracts,
        "chain": chain,
        "assumptions": assumptions,
        "missing": missing,
        "budget": round(budget) if budget else None,
        "baseline_confidence": base["confidence"],
        "baseline_months": base["months_used"],
        "sensitivity": _sensitivity(target_contracts, lead_to_visit, visit_to_contract, cpl),
    }


def _sensitivity(
    target: int, lead_to_visit: float | None, visit_to_contract: float | None, cpl: float | None
) -> list[dict]:
    """«Agar konversiya 1 punktga oshsa, nima o'zgaradi» — reja qayerga
    sezgir ekanini ko'rsatadi.

    Nega PUNKT (foiz emas): «10% oshsa» degani noaniq (10% dan 11% mi yoki
    10% dan 10.1% mi). Punkt aniq: 10% -> 11%."""
    if not lead_to_visit or not visit_to_contract:
        return []

    def leads_for(ltv: float, vtc: float) -> float:
        return target / (vtc / 100) / (ltv / 100)

    base_leads = leads_for(lead_to_visit, visit_to_contract)
    out = []
    for label, ltv, vtc in (
        ("Tashrif→shartnoma +1 punkt", lead_to_visit, visit_to_contract + 1),
        ("Lid→tashrif +1 punkt", lead_to_visit + 1, visit_to_contract),
    ):
        new_leads = leads_for(ltv, vtc)
        diff = base_leads - new_leads
        out.append(
            {
                "label": label,
                "leads_saved": _up(diff) if diff > 0 else 0,
                "budget_saved": round(diff * cpl) if cpl and diff > 0 else None,
            }
        )
    return out


async def get_target(db: AsyncSession, period: str) -> FunnelMonth | None:
    return await db.get(FunnelMonth, period)


async def save_target(
    db: AsyncSession,
    period: str,
    target_contracts: int | None,
    assumptions: dict | None,
    actor_id: int | None,
) -> FunnelMonth:
    row = await db.get(FunnelMonth, period)
    if row is None:
        row = FunnelMonth(period=period)
        db.add(row)
    row.target_contracts = target_contracts
    # Faqat to'ldirilgan kalitlar saqlanadi — bo'shlari o'lchangan qiymatdan
    # olinaveradi (shunda o'lchov yangilansa reja ham yangilanadi).
    row.assumptions = {k: v for k, v in (assumptions or {}).items() if v is not None} or None
    row.updated_by = actor_id
    await db.commit()
    await db.refresh(row)
    return row
