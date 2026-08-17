"""Bo'g'in tahlili va stsenariylar — voronka 7-bosqich (1 va 2-band).

Reja: `VORONKA_TARGET_REJASI.html` 07-bosqich:
  • «Eng katta yo'qotish qayerda (bo'g'in tahlili)»
  • «Agar byudjetni 20% oshirsak, nechta uy qo'shiladi»

IKKI SAVOL, IKKI JAVOB:
  1. YO'QOTISH — o'tmishga qaraydi: qaysi bosqichda qancha lid tushib
     qoldi va bu qancha pulga tushdi.
  2. STSENARIY — kelajakka qaraydi: bitta narsani o'zgartirsak natija
     qanday bo'ladi.

PULGA AYLANTIRISH QOIDASI: yo'qolgan lidning qiymati = CPL. Ya'ni har bir
lid uchun reklama puli ALLAQACHON to'langan, u qaysi bosqichda tushib
qolganidan qat'i nazar. CPL o'lchanmagan bo'lsa — pul umuman
ko'rsatilmaydi (`None`), taxminiy narx o'ylab topilmaydi.

«YO'QOTILGAN SHARTNOMA» — shartli baho: yo'qolgan lidlar o'rtacha
konversiya bilan davom etganda nechta shartnoma bo'lardi. Bu ANIQ raqam
emas, kattalik tartibi; nomida ham «~» bilan ko'rsatiladi.
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from api.services import funnel as funnel_service
from api.services import target_calc

# Stsenariylardagi standart byudjet o'sishi (reja shu misolni keltirgan).
DEFAULT_BUDGET_STEP = 20


def _period_bounds(period: str) -> tuple[date, date]:
    year, month = (int(p) for p in period.split("-"))
    start = date(year, month, 1)
    end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return start, end - timedelta(days=1)


def _pct(part: int, whole: int) -> float | None:
    if not whole:
        return None
    return round(part * 100 / whole, 1)


async def leak_analysis(db: AsyncSession, period: str) -> dict:
    """Bo'g'in tahlili — qayerda qancha lid yo'qolyapti va bu qancha pul.

    KOGORTA bo'yicha: «shu oyda kelgan lidlarning qanchasi qaysi bosqichda
    tushib qoldi». Davr kesimi bu yerda ma'nosiz — u yerda maxraj va surat
    turli lidlarga tegishli bo'lib, «yo'qotish» soxta chiqardi."""
    start, end = _period_bounds(period)
    today = date.today()
    data = await funnel_service.cohort_funnel(db, start, min(end, today))
    rows = {r["key"]: r["value"] for r in data["rows"]}

    base = await target_calc.baseline(db)
    cpl = base["values"].get("cpl")

    # Zanjir: lid -> taklif -> tashrif -> shartnoma
    chain = [
        ("lead", funnel_service.STAGE_INVITE, "Lid → ofisga taklif"),
        (funnel_service.STAGE_INVITE, funnel_service.STAGE_VISIT, "Taklif → tashrif"),
        (funnel_service.STAGE_VISIT, funnel_service.STAGE_CONTRACT, "Tashrif → shartnoma"),
    ]
    total_leads = rows.get("lead", 0)
    contracts = rows.get(funnel_service.STAGE_CONTRACT, 0)
    # Umumiy lid→shartnoma konversiyasi — «yo'qolgan shartnoma» bahosi uchun
    overall = (contracts / total_leads) if total_leads else None

    steps = []
    for from_key, to_key, label in chain:
        entered = rows.get(from_key, 0)
        passed = rows.get(to_key, 0)
        lost = max(0, entered - passed)
        steps.append(
            {
                "label": label,
                "entered": entered,
                "passed": passed,
                "lost": lost,
                "loss_pct": _pct(lost, entered),
                "pass_pct": _pct(passed, entered),
                # Yo'qolgan lidlarning reklama qiymati
                "money_lost": round(lost * cpl) if cpl and lost else None,
                # Shu bosqichda yo'qolganlar o'rtacha konversiya bilan
                # davom etganda nechta shartnoma bo'lardi (SHARTLI baho)
                "contracts_lost": (
                    round(lost * overall, 1) if overall and lost else None
                ),
            }
        )

    biggest = max(steps, key=lambda s: s["lost"]) if steps and total_leads else None
    return {
        "period": period,
        "total_leads": total_leads,
        "contracts": contracts,
        "overall_conversion": _pct(contracts, total_leads),
        "cpl": cpl,
        "steps": steps,
        "biggest_leak": {"label": biggest["label"], "lost": biggest["lost"]}
        if biggest and biggest["lost"]
        else None,
        "mature": data.get("mature"),
        "note": (
            "«~yo'qolgan shartnoma» — shartli baho: yo'qolgan lidlar o'rtacha "
            "konversiya bilan davom etganda nechta shartnoma bo'lardi."
        ),
    }


async def scenarios(
    db: AsyncSession, period: str, budget_step_pct: int = DEFAULT_BUDGET_STEP
) -> dict:
    """«Agar ...» stsenariylari — bitta narsani o'zgartirsak natija qanday.

    Har bir stsenariyning KIRISHI aniq ko'rsatiladi: qaysi faraz
    ishlatilgani va u o'lchanganmi yoki taxminiymi. Taxminiy farazdan
    chiqqan «+3 uy» va o'lchangan farazdan chiqqan «+3 uy» — bir xil
    ishonchga ega emas."""
    saved = await target_calc.get_target(db, period)
    target = saved.target_contracts if saved else None

    base = await target_calc.baseline(db)
    measured = base["values"]
    overrides = (saved.assumptions if saved else None) or {}

    lead_to_visit, src_ltv = target_calc._resolve(  # noqa: SLF001
        "lead_to_visit", overrides, measured
    )
    visit_to_contract, src_vtc = target_calc._resolve(  # noqa: SLF001
        "visit_to_contract", overrides, measured
    )
    cpl, src_cpl = target_calc._resolve("cpl", overrides, measured)  # noqa: SLF001

    lead_to_contract = (
        (lead_to_visit / 100) * (visit_to_contract / 100)
        if lead_to_visit and visit_to_contract
        else None
    )

    out: list[dict] = []

    # ── 1. Byudjetni oshirish ──
    if cpl and lead_to_contract and target:
        current_budget = target / lead_to_contract * cpl
        extra_budget = current_budget * budget_step_pct / 100
        extra_leads = extra_budget / cpl
        extra_contracts = extra_leads * lead_to_contract
        out.append(
            {
                "key": "budget_up",
                "label": f"Byudjet +{budget_step_pct}%",
                "detail": f"+{round(extra_budget):,} so'm".replace(",", " "),
                "extra_leads": round(extra_leads),
                "extra_contracts": round(extra_contracts, 1),
                "sources": [src_cpl, src_ltv, src_vtc],
            }
        )
    else:
        out.append(
            {
                "key": "budget_up",
                "label": f"Byudjet +{budget_step_pct}%",
                "detail": None,
                "extra_leads": None,
                "extra_contracts": None,
                "missing": [
                    k
                    for k, v in (("cpl", cpl), ("maqsad", target), ("konversiya", lead_to_contract))
                    if not v
                ],
                "sources": [src_cpl],
            }
        )

    # ── 2. Konversiyani yaxshilash (har biri +1 punkt) ──
    if target and lead_to_visit and visit_to_contract:
        for label, ltv, vtc, src in (
            ("Tashrif → shartnoma +1 punkt", lead_to_visit, visit_to_contract + 1, src_vtc),
            ("Lid → tashrif +1 punkt", lead_to_visit + 1, visit_to_contract, src_ltv),
        ):
            new_conv = (ltv / 100) * (vtc / 100)
            # Bir xil lid oqimida nechta shartnoma ko'proq bo'ladi
            leads_now = target / lead_to_contract if lead_to_contract else None
            extra = (leads_now * new_conv - target) if leads_now else None
            saved_budget = (
                (target / lead_to_contract - target / new_conv) * cpl
                if cpl and lead_to_contract and new_conv
                else None
            )
            out.append(
                {
                    "key": label,
                    "label": label,
                    "detail": "bir xil lid oqimida",
                    "extra_leads": None,
                    "extra_contracts": round(extra, 1) if extra is not None else None,
                    "budget_saved": round(saved_budget) if saved_budget else None,
                    "sources": [src],
                }
            )

    return {
        "period": period,
        "target_contracts": target,
        "assumptions": {
            "lead_to_visit": {"value": lead_to_visit, "source": src_ltv},
            "visit_to_contract": {"value": visit_to_contract, "source": src_vtc},
            "cpl": {"value": cpl, "source": src_cpl},
        },
        "scenarios": out,
        "confidence": base["confidence"],
    }
