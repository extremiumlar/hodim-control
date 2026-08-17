"""Reja va fakt kuzatuvi + prognoz — voronka 6-bosqich.

Reja: `VORONKA_TARGET_REJASI.html` 06-bosqich — «oy oxirini kutmaslik».

SAVOL: «shu tempda oy oxirida nechta bo'ladi?» Javob oyning 10-kunida
kerak, 30-kunida emas.

TEMP ISH KUNI BO'YICHA O'LCHANADI, KALENDAR KUNI BO'YICHA EMAS. Sabab:
oyning birinchi 10 kunida 3 ta dam olish bo'lishi mumkin, keyingi 10 kunida
bittasi ham yo'q — kalendar bo'yicha «33% vaqt o'tdi» desak, reja
bajarilishi sun'iy past yoki yuqori ko'rinardi. Shuning uchun o'tgan ULUSH =
o'tgan ish-kunlari ÷ oyning barcha ish-kunlari (5-bosqichdagi
`target_split` bilan AYNAN bir xil manba).

PROGNOZ = haqiqiy ÷ o'tgan ulush. Ya'ni «shu tempda davom etsa oy oxirida
shuncha bo'ladi». Oy boshida (ulush juda kichik) prognoz beqaror bo'ladi —
shuning uchun `MIN_ELAPSED_FOR_FORECAST` gacha prognoz KO'RSATILMAYDI:
2 kunlik ma'lumotdan «oy oxirida 3 ta bo'ladi» deb qo'rqitish noto'g'ri.
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.services import funnel as funnel_service
from api.services import payroll as payroll_service
from api.services import target_calc, target_split
from db.models import User

# Oyning shuncha ulushi o'tmaguncha prognoz ko'rsatilmaydi (juda kichik
# namunadan qilingan prognoz chalg'itadi).
MIN_ELAPSED_FOR_FORECAST = 0.2

# Rejadan shuncha ulushdan pastda bo'lsa «orqada» deb belgilanadi.
BEHIND_THRESHOLD = 0.9

# Voronka zanjiridagi qator -> davr kesimidagi qator (fakt manbai)
PLAN_TO_ACTUAL = {
    "leads": "lead",
    "talks": "call_talk",
    "visits": "visit",
    "contracts": "contract",
}

LABELS = {
    "leads": "Lid",
    "talks": "Suhbat",
    "visits": "Tashrif",
    "contracts": "Shartnoma (uy)",
}


def _period_bounds(period: str) -> tuple[date, date]:
    year, month = (int(p) for p in period.split("-"))
    start = date(year, month, 1)
    end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return start, end - timedelta(days=1)


async def _elapsed_share(db: AsyncSession, period: str, today: date) -> dict:
    """Oyning qancha ULUSHI o'tgan — ish kunlari bo'yicha.

    Kuzatiladigan xodimlarning (suhbat yoki tashrif metrikasi bor) rejadagi
    ish kunlari yig'indisi olinadi: shu oy jami va bugungacha. Xodim ta'tilda
    bo'lsa uning kunlari ikkalasidan ham chiqadi — ya'ni «kam odam ishlagan»
    davr rejani sun'iy ravishda orqada ko'rsatmaydi."""
    from api.routers.norms import metrics_for

    start, end = _period_bounds(period)
    users = list(await db.scalars(select(User).where(User.is_active.is_(True))))
    tracked = [u for u in users if set(metrics_for(u)) & {"suhbat", "tashrif"}]
    excused = await target_split._excused_map(db, period)  # noqa: SLF001

    total = 0
    passed = 0
    for user in tracked:
        skip = excused.get(user.id, set())
        days = await payroll_service.month_schedule(db, user, period)
        for d in days:
            if not d["is_working"] or d["date"] in skip:
                continue
            total += 1
            if d["date"] <= today:
                passed += 1

    if not total:
        # Ish jadvali umuman yo'q — kalendar kuniga qaytamiz (yomonroq,
        # lekin hech qanday prognoz bermaslikdan yaxshiroq).
        cal_total = (end - start).days + 1
        cal_passed = max(0, min((today - start).days + 1, cal_total))
        return {
            "share": round(cal_passed / cal_total, 3) if cal_total else 0.0,
            "basis": "kalendar",
            "days_passed": cal_passed,
            "days_total": cal_total,
        }

    return {
        "share": round(passed / total, 3),
        "basis": "ish kuni",
        "days_passed": passed,
        "days_total": total,
    }


async def progress(db: AsyncSession, period: str, today: date | None = None) -> dict:
    """Reja / haqiqiy / farq + oy oxiri prognozi."""
    today = today or date.today()
    start, end = _period_bounds(period)

    saved = await target_calc.get_target(db, period)
    if saved is None or not saved.target_contracts:
        return {
            "period": period,
            "ready": False,
            "reason": "Bu oy uchun maqsad qo'yilmagan — kuzatish uchun avval maqsad kerak",
            "rows": [],
        }

    plan = await target_calc.calculate(
        db, period, saved.target_contracts, saved.assumptions or {}
    )
    plan_chain = {c["key"]: c["value"] for c in plan["chain"]}

    # FAKT: davr kesimi (shu oy ichida sodir bo'lgani) — operativ savol
    # aynan shu, kogorta emas.
    actual_to = min(today, end)
    actual = await funnel_service.period_funnel(db, start, actual_to)
    actual_by = {r["key"]: r["value"] for r in actual["rows"]}

    elapsed = await _elapsed_share(db, period, today)
    share = elapsed["share"]
    forecast_ready = share >= MIN_ELAPSED_FOR_FORECAST

    rows = []
    for plan_key, actual_key in PLAN_TO_ACTUAL.items():
        plan_value = plan_chain.get(plan_key)
        fact = actual_by.get(actual_key, 0)
        expected = round(plan_value * share) if plan_value else None
        forecast = round(fact / share) if forecast_ready and share > 0 else None

        if plan_value and expected is not None:
            if fact >= expected:
                status = "yaxshi"
            elif expected and fact < expected * BEHIND_THRESHOLD:
                status = "orqada"
            else:
                status = "chegarada"
        else:
            status = "noma'lum"

        rows.append(
            {
                "key": plan_key,
                "label": LABELS[plan_key],
                "plan_month": plan_value,
                "expected_now": expected,
                "actual": fact,
                "diff": (fact - expected) if expected is not None else None,
                "forecast": forecast,
                "forecast_gap": (forecast - plan_value)
                if forecast is not None and plan_value
                else None,
                "status": status,
            }
        )

    # Qaysi bo'g'in eng ko'p orqada — rejaga nisbatan ULUSHI eng past bo'lgani
    behind = [r for r in rows if r["expected_now"] and r["status"] == "orqada"]
    weakest = (
        min(behind, key=lambda r: r["actual"] / r["expected_now"]) if behind else None
    )

    return {
        "period": period,
        "ready": True,
        "target_contracts": saved.target_contracts,
        "elapsed": elapsed,
        "forecast_ready": forecast_ready,
        "min_elapsed": MIN_ELAPSED_FOR_FORECAST,
        "rows": rows,
        "weakest": {"key": weakest["key"], "label": weakest["label"]} if weakest else None,
        "baseline_confidence": plan["baseline_confidence"],
    }


def digest_line(data: dict) -> str | None:
    """Guruh digestiga qo'shiladigan BIR-IKKI qator.

    Reja: «Mavjud guruh digestiga qo'shiladi (yangi kanal qurish shart emas)».
    Maqsad qo'yilmagan bo'lsa yoki prognoz hali beqaror bo'lsa — jim
    qolamiz: har kuni «ma'lumot yetarli emas» deb yozish shovqin."""
    if not data.get("ready") or not data.get("forecast_ready"):
        return None

    by_key = {r["key"]: r for r in data["rows"]}
    contracts = by_key.get("contracts")
    if not contracts or not contracts["plan_month"]:
        return None

    forecast = contracts["forecast"]
    plan_month = contracts["plan_month"]
    fact = contracts["actual"]
    share_pct = round(data["elapsed"]["share"] * 100)

    if forecast is None:
        return None

    if forecast >= plan_month:
        head = f"🎯 <b>Reja bo'yicha</b>: shu tempda oy oxirida ~{forecast} ta (maqsad {plan_month})"
    else:
        head = (
            f"⚠️ <b>Reja ostida</b>: shu tempda oy oxirida ~{forecast} ta bo'ladi, "
            f"maqsad {plan_month} ta"
        )

    lines = [head, f"   Hozircha: {fact} ta · oyning {share_pct}% ish kuni o'tdi"]
    weakest = data.get("weakest")
    if weakest:
        lines.append(f"   Eng orqada: {weakest['label']}")
    return "\n".join(lines)
