"""Operator kesimida konversiya — «kim yaxshi yopadi» (voronka 7-bosqich, 3-band).

Reja: `VORONKA_TARGET_REJASI.html` 07-bosqich · Ta'riflar: `VORONKA_TARIFLAR.md`

MAVJUD STATISTIKADAN FARQI: tizim bugun ham «kim nechta tashrif qildi» ni
ko'rsatadi — bu MEHNAT HAJMI. Bu modul esa SIFATNI o'lchaydi: «bergan
lidining qanchasini tashrifga aylantirdi». 24 ta tashrif qilgan operator
300 ta lid olgan bo'lsa, 12 ta tashrif qilgan 80 ta lidlik operatordan
YOMONROQ ishlagan bo'lishi mumkin.

IKKI ROL, IKKI SAVOL — ATAYLAB AJRATILGAN:
  • OPERATOR: lid → tashrif. Maxraj — u OLIB KELGAN lidlar
    (`CrmLeadState.first_responsible_id`), ya'ni «o'z lidining qanchasini
    ofisga keltira oldi».
  • MENEJER: tashrif → shartnoma. Maxraj — u O'ZI qabul qilgan tashriflar
    (tashrif voqeasidagi `to_responsible_id`), ya'ni «kelgan mijozning
    qanchasini yopa oldi».
Ikkalasini bitta jadvalga qo'shish noto'g'ri bo'lardi: ular boshqa-boshqa
ishni bajaradi va bir-biri bilan taqqoslanmaydi.

KICHIK NAMUNA MASALASI: 3 ta liddan 1 tasi tashrifga aylansa «33%» chiqadi
va u eng zo'r bo'lib ko'rinadi. Shuning uchun `MIN_SAMPLE` dan kam namunali
qator reytingga KIRITILMAYDI (jadvalda ko'rinadi, lekin «namuna kichik»
belgisi bilan va eng yaxshi/yomon tanlovida qatnashmaydi).
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.services import funnel as funnel_service
from api.timeutil import local_range_utc_naive
from db.models import CrmLeadState, HourlyActual, LeadEvent, User

# Reytingga kirish uchun eng kam namuna. Bulardan kam bo'lsa foiz
# tasodifga bog'liq bo'lib qoladi va odamni nohaq ayblash yoki nohaq
# maqtash xavfi tug'iladi.
MIN_LEADS_FOR_RANK = 20
MIN_VISITS_FOR_RANK = 5


def _pct(numerator: int, denominator: int) -> float | None:
    if not denominator:
        return None
    return round(numerator * 100 / denominator, 1)


async def _users_by_crm_id(db: AsyncSession) -> dict[str, User]:
    rows = await db.scalars(select(User).where(User.crm_visit_external_id.isnot(None)))
    return {u.crm_visit_external_id: u for u in rows}


async def _calls_by_user(db: AsyncSession, day_from: date, day_to: date) -> dict[int, dict]:
    rows = await db.execute(
        select(
            HourlyActual.user_id,
            func.coalesce(func.sum(HourlyActual.calls), 0),
            func.coalesce(func.sum(HourlyActual.answered), 0),
            func.coalesce(func.sum(HourlyActual.talk_sec), 0),
        )
        .where(HourlyActual.date >= day_from, HourlyActual.date <= day_to)
        .group_by(HourlyActual.user_id)
    )
    return {
        int(uid): {"calls": int(c or 0), "answered": int(a or 0), "talk_sec": int(t or 0)}
        for uid, c, a, t in rows
    }


async def operator_quality(db: AsyncSession, day_from: date, day_to: date) -> dict:
    """Operator va menejer kesimida konversiya (kogorta mantig'ida).

    Kogorta: shu davrda KELGAN lidlar bo'yicha — «bu oyda olgan lidining
    qanchasini aylantirdi». Davr kesimi bu yerda chalg'itardi: operator
    o'tgan oyning lidini bugun tashrifga olib kelsa, bugungi konversiyasi
    100% dan oshib ketardi."""
    start_utc, end_utc = local_range_utc_naive(day_from, day_to)
    lead_ids, _approx = await funnel_service._cohort_lead_ids(db, start_utc, end_utc)  # noqa: SLF001

    users = await _users_by_crm_id(db)
    calls = await _calls_by_user(db, day_from, day_to)

    visit_ids = await funnel_service._lead_ids_ever_reached(  # noqa: SLF001
        db, funnel_service.STAGE_VISIT, lead_ids
    )
    contract_ids = await funnel_service._lead_ids_ever_reached(  # noqa: SLF001
        db, funnel_service.STAGE_CONTRACT, lead_ids
    )

    # ── OPERATOR: lid -> tashrif (maxraj — OLIB KELGAN lidlari) ──
    by_operator: dict[int, set[int]] = {}
    if lead_ids:
        rows = await db.execute(
            select(CrmLeadState.crm_lead_id, CrmLeadState.first_responsible_id).where(
                CrmLeadState.crm_lead_id.in_(lead_ids),
                CrmLeadState.first_responsible_id.isnot(None),
            )
        )
        for lead_id, rid in rows:
            by_operator.setdefault(int(rid), set()).add(lead_id)

    operators = []
    for rid, ids in by_operator.items():
        user = users.get(str(rid))
        leads = len(ids)
        visits = len(ids & visit_ids)
        contracts = len(ids & contract_ids)
        c = calls.get(user.id, {}) if user else {}
        operators.append(
            {
                "responsible_id": rid,
                "user_id": user.id if user else None,
                "full_name": user.full_name.strip() if user else f"CRM #{rid}",
                "leads": leads,
                "visits": visits,
                "contracts": contracts,
                "lead_to_visit": _pct(visits, leads),
                "calls": c.get("calls"),
                "answered": c.get("answered"),
                # Bitta tashrif uchun nechta suhbat kerak bo'ldi — mehnat
                # unumdorligining boshqa tomoni
                "talks_per_visit": (
                    round(c["answered"] / visits, 1) if c.get("answered") and visits else None
                ),
                "ranked": leads >= MIN_LEADS_FOR_RANK,
            }
        )
    operators.sort(key=lambda r: (-(r["lead_to_visit"] or -1), -r["leads"]))

    # ── MENEJER: tashrif -> shartnoma (maxraj — O'ZI qabul qilgan tashriflar) ──
    manager_visits: dict[int, set[int]] = {}
    if lead_ids:
        ids_at_visit = funnel_service._ids_at_or_after(funnel_service.STAGE_VISIT)  # noqa: SLF001
        rows = await db.scalars(
            select(LeadEvent).where(
                LeadEvent.crm_lead_id.in_(lead_ids),
                LeadEvent.event_type != "first_seen",
                LeadEvent.to_pipe_status_id.in_(ids_at_visit),
                LeadEvent.from_pipe_status_id.notin_(ids_at_visit)
                | LeadEvent.from_pipe_status_id.is_(None),
                LeadEvent.to_responsible_id.isnot(None),
            )
        )
        for ev in rows:
            manager_visits.setdefault(int(ev.to_responsible_id), set()).add(ev.crm_lead_id)

    managers = []
    for rid, ids in manager_visits.items():
        user = users.get(str(rid))
        visits = len(ids)
        contracts = len(ids & contract_ids)
        managers.append(
            {
                "responsible_id": rid,
                "user_id": user.id if user else None,
                "full_name": user.full_name.strip() if user else f"CRM #{rid}",
                "visits": visits,
                "contracts": contracts,
                "visit_to_contract": _pct(contracts, visits),
                "ranked": visits >= MIN_VISITS_FOR_RANK,
            }
        )
    managers.sort(key=lambda r: (-(r["visit_to_contract"] or -1), -r["visits"]))

    return {
        "date_from": day_from.isoformat(),
        "date_to": day_to.isoformat(),
        "operators": operators,
        "managers": managers,
        "best_operator": _best(operators, "lead_to_visit"),
        "worst_operator": _worst(operators, "lead_to_visit"),
        "best_manager": _best(managers, "visit_to_contract"),
        "min_leads": MIN_LEADS_FOR_RANK,
        "min_visits": MIN_VISITS_FOR_RANK,
        "note": (
            "Konversiya — SIFAT o'lchovi: «o'z lidining qanchasini aylantirdi». "
            "Soni ko'p bo'lgan xodim konversiyasi past bo'lishi mumkin."
        ),
    }


def _ranked(rows: list[dict], key: str) -> list[dict]:
    return [r for r in rows if r["ranked"] and r[key] is not None]


def _best(rows: list[dict], key: str) -> dict | None:
    pool = _ranked(rows, key)
    return max(pool, key=lambda r: r[key]) if pool else None


def _worst(rows: list[dict], key: str) -> dict | None:
    """Eng past konversiya — faqat YETARLI namunali qatorlar orasidan.

    Ikki kishidan kam bo'lsa «eng yomon» degan tushuncha ma'nosiz
    (yagona odam bir vaqtda eng yaxshi ham, eng yomon ham bo'lib qoladi)."""
    pool = _ranked(rows, key)
    return min(pool, key=lambda r: r[key]) if len(pool) >= 2 else None
