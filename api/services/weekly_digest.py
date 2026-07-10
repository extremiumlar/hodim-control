"""Haftalik yakun digesti — guruhga BITTA jamlangan xabar, sof KOD hisobi.

AI'dagi haftalik trend (ai_coach.weekly_trend — operatorga shaxsiy xabar) dan farqi:
bu digest AI umuman o'chiq bo'lsa ham ishlaydi va guruhga RAQAMLI hafta yakunini
beradi — operator kesimida qo'ng'iroq/lid/tashrif/vazifa, o'tgan haftaga nisbatan
% o'zgarish, eng o'sgan va eng pasaygan operator. Ma'lumot tayyor kunlik snapshot
jadvallaridan (LeadStageDaily, OperatorCallsDaily) — CRM'ga murojaat yo'q.

Taqqoslash: "shu hafta" = ref_day bilan tugaydigan 7 kun, "o'tgan hafta" = undan
oldingi 7 kun (api/services/weekly_stats.py bilan bir xil konventsiya)."""
import html
from datetime import date, timedelta

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import settings
from api.telegram_notify import send_message
from api.timeutil import local_range_utc_naive, today_local
from db.models import (
    LeadStageDaily,
    OperatorCallsDaily,
    Role,
    TaskModel,
    TaskStatus,
    User,
)

# "Tashrif" bosqichi nom bo'yicha (api/routers/stats.py va daily_digest bilan bir xil)
_VISIT_STAGE_NAME = "tashrif"

# % o'zgarishni ko'rsatish uchun o'tgan haftada kamida shuncha qo'ng'iroq bo'lsin —
# aks holda kichik bazadan katta % chiqib chalg'itadi (5 → 15 qo'ng'iroq "+200%").
_MIN_PREV_CALLS_FOR_PCT = 10


async def _range_by_operator(db: AsyncSession, day_from: date, day_to: date) -> dict[int, dict]:
    """[day_from, day_to] oralig'ining operator kesimi:
    {responsible_id: {name, calls, leads, visits}} — ikkita grouped so'rov."""
    agg: dict[int, dict] = {}

    is_visit = func.lower(func.trim(LeadStageDaily.stage_name)) == _VISIT_STAGE_NAME
    lead_rows = await db.execute(
        select(
            LeadStageDaily.responsible_id,
            func.max(LeadStageDaily.responsible_name),
            func.sum(LeadStageDaily.leads_count),
            func.sum(case((is_visit, LeadStageDaily.leads_count), else_=0)),
        )
        .where(LeadStageDaily.date >= day_from, LeadStageDaily.date <= day_to)
        .group_by(LeadStageDaily.responsible_id)
    )
    for rid, name, leads, visits in lead_rows.all():
        agg[rid] = {"name": name, "calls": 0, "leads": int(leads or 0), "visits": int(visits or 0)}

    call_rows = await db.execute(
        select(
            OperatorCallsDaily.responsible_id,
            func.max(OperatorCallsDaily.responsible_name),
            func.sum(OperatorCallsDaily.calls_in + OperatorCallsDaily.calls_out),
        )
        .where(OperatorCallsDaily.date >= day_from, OperatorCallsDaily.date <= day_to)
        .group_by(OperatorCallsDaily.responsible_id)
    )
    for rid, name, calls in call_rows.all():
        a = agg.setdefault(rid, {"name": name, "calls": 0, "leads": 0, "visits": 0})
        a["calls"] += int(calls or 0)
        if not a.get("name"):
            a["name"] = name

    return agg


async def _tasks_by_user(db: AsyncSession, day_from: date, day_to: date) -> dict[int, tuple[int, int]]:
    """Oraliqda berilgan vazifalar: {user_id: (bajarilgan, jami)}."""
    start_utc, end_utc = local_range_utc_naive(day_from, day_to)
    rows = await db.execute(
        select(
            TaskModel.assigned_to,
            func.count(TaskModel.id),
            func.sum(case((TaskModel.status == TaskStatus.done.value, 1), else_=0)),
        )
        .where(TaskModel.created_at >= start_utc, TaskModel.created_at < end_utc)
        .group_by(TaskModel.assigned_to)
    )
    return {uid: (int(done or 0), int(total)) for uid, total, done in rows.all()}


def _pct_change(cur: int, prev: int | None) -> int | None:
    """O'tgan haftaga nisbatan % o'zgarish — baza yetarli bo'lsagina."""
    if prev is None or prev < _MIN_PREV_CALLS_FOR_PCT:
        return None
    return round((cur - prev) / prev * 100)


def _pct_str(pct: int | None) -> str:
    if pct is None:
        return ""
    sign = "+" if pct > 0 else ""
    return f" ({sign}{pct}%)"


async def build_weekly_digest(db: AsyncSession, ref_day: date | None = None) -> dict:
    """Digest matnini quradi (yubormaydi). Qaytaradi: {"text", "operators"} —
    haftada umuman faoliyat bo'lmasa text=None."""
    ref_day = ref_day or today_local()
    this_start = ref_day - timedelta(days=6)
    prev_start = this_start - timedelta(days=7)
    prev_end = this_start - timedelta(days=1)

    this_week = await _range_by_operator(db, this_start, ref_day)
    prev_week = await _range_by_operator(db, prev_start, prev_end)
    tasks = await _tasks_by_user(db, this_start, ref_day)

    employees = list(
        await db.scalars(
            select(User).where(User.role == Role.employee.value, User.is_active == True)  # noqa: E712
        )
    )
    user_by_rid: dict[int, User] = {}
    for u in employees:
        try:
            if u.crm_visit_external_id:
                user_by_rid[int(u.crm_visit_external_id)] = u
        except (TypeError, ValueError):
            continue

    active = {rid: a for rid, a in this_week.items() if a["calls"] or a["leads"]}
    if not active:
        return {"text": None, "operators": 0}

    lines: list[str] = []
    changes: list[tuple[str, int]] = []  # (ism, %-o'zgarish) — eng o'sish/pasayish uchun
    for rid, a in sorted(active.items(), key=lambda x: -(x[1]["calls"] + x[1]["leads"])):
        user = user_by_rid.get(rid)
        name = html.escape((user.full_name if user else a["name"]) or str(rid))
        prev = prev_week.get(rid)
        pct = _pct_change(a["calls"], prev["calls"] if prev else None)
        if pct is not None and rid in user_by_rid:  # "Boshqa" (rid=0) reytingga kirmaydi
            changes.append((name, pct))

        task_part = ""
        if user is not None and user.id in tasks:
            done, total = tasks[user.id]
            mark = "✅" if done == total else "🕓"
            task_part = f" · {mark} {done}/{total}"
        lines.append(
            f"• <b>{name}</b> — 📞 {a['calls']}{_pct_str(pct)} · 🧲 {a['leads']} · 🏠 {a['visits']}{task_part}"
        )

    total_calls = sum(a["calls"] for a in active.values())
    total_leads = sum(a["leads"] for a in active.values())
    total_visits = sum(a["visits"] for a in active.values())
    prev_total_calls = sum(a["calls"] for a in prev_week.values())
    total_pct = _pct_change(total_calls, prev_total_calls if prev_week else None)
    totals = f"<b>Jami:</b> 📞 {total_calls}"
    if prev_week:
        totals += f" (o'tgan hafta {prev_total_calls}{_pct_str(total_pct)})"
    totals += f" · 🧲 {total_leads} · 🏠 {total_visits}"

    parts = [
        f"📈 <b>Haftalik yakun — {this_start:%d.%m} – {ref_day:%d.%m.%Y}</b>",
        "",
        *lines,
        "",
        totals,
    ]
    if changes:
        best = max(changes, key=lambda x: x[1])
        worst = min(changes, key=lambda x: x[1])
        rating = []
        if best[1] > 0:
            rating.append(f"📈 Eng o'sish: {best[0]} (+{best[1]}%)")
        if worst[1] < 0 and worst[0] != best[0]:
            rating.append(f"📉 Eng pasayish: {worst[0]} ({worst[1]}%)")
        if rating:
            parts.append(" · ".join(rating))
    parts.append("")
    parts.append("<i>📞 qo'ng'iroq (o'tgan haftaga nisbatan) · 🧲 ishlangan lid · 🏠 tashrif · ✅ vazifa</i>")

    return {"text": "\n".join(parts), "operators": len(active)}


async def send_weekly_digest(db: AsyncSession, chat_id: int | None = None, dry_run: bool = False) -> dict:
    """Haftalik digestni quradi va yuboradi. `chat_id` berilmasa — umumiy guruhga."""
    digest = await build_weekly_digest(db)
    if digest["text"] is None:
        return {"sent": False, "reason": "Bu hafta uchun ma'lumot topilmadi", "operators": 0}

    if dry_run:
        return {"sent": False, "dry_run": True, "operators": digest["operators"], "text": digest["text"]}

    target_chat = chat_id or settings.telegram_group_chat_id
    if not target_chat:
        return {"sent": False, "reason": "Guruh chat ID sozlanmagan", "operators": digest["operators"]}

    ok = await send_message(target_chat, digest["text"])
    return {"sent": ok is not None, "operators": digest["operators"]}
