"""Oylik yakun digesti — guruhga BITTA jamlangan xabar, sof KOD hisobi.

Haftalik digest bilan bir xil uslub, lekin taqqoslash KALENDAR oylar kesimida:
joriy oy (1-sanadan ref kungacha) vs o'tgan TO'LIQ oy. Scheduler oyning oxirgi
kuni kechqurun chaqiradi — o'shanda ikkala davr deyarli teng uzunlikda bo'ladi
(oy o'rtasida qo'lda chaqirilsa % ehtiyot bilan o'qilsin — matnda davr aniq
yoziladi). Qo'shimcha: Bonus jadvalida joriy oy uchun hisoblangan bonus bo'lsa
operator qatorida va jami satrida ko'rsatiladi (bonus odatda oyning oxirgi kuni
23:30 da hisoblanadi — digest 20:30 da chiqsa hali bo'lmaydi, bu normal)."""
import html
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.services.daily_digest import digest_group_targets
from api.services.weekly_digest import _pct_change, _pct_str, _range_by_operator, _tasks_by_user
from api.telegram_notify import send_message
from api.timeutil import today_local
from db.models import Bonus, HourlyActual, Role, User

MONTH_NAMES_UZ = {
    1: "Yanvar", 2: "Fevral", 3: "Mart", 4: "Aprel", 5: "May", 6: "Iyun",
    7: "Iyul", 8: "Avgust", 9: "Sentabr", 10: "Oktabr", 11: "Noyabr", 12: "Dekabr",
}


def _fmt_talk(sec: int) -> str:
    minutes = sec // 60
    hours, minutes = divmod(minutes, 60)
    return f"{hours}s {minutes}d" if hours else f"{minutes}d"


def _fmt_money(amount: float) -> str:
    """1200000.0 → '1 200 000' (so'm belgisisiz — xabarda 💰 bilan chiqadi)."""
    return f"{amount:,.0f}".replace(",", " ")


async def build_monthly_digest(db: AsyncSession, ref_day: date | None = None) -> dict:
    """Digest matnini quradi (yubormaydi). Qaytaradi: {"text", "operators"} —
    oyda umuman faoliyat bo'lmasa text=None."""
    ref_day = ref_day or today_local()
    month_start = ref_day.replace(day=1)
    prev_end = month_start - timedelta(days=1)
    prev_start = prev_end.replace(day=1)
    period_key = ref_day.strftime("%Y-%m")

    current = await _range_by_operator(db, month_start, ref_day)
    previous = await _range_by_operator(db, prev_start, prev_end)
    tasks = await _tasks_by_user(db, month_start, ref_day)

    talk_rows = await db.execute(
        select(HourlyActual.user_id, func.sum(HourlyActual.talk_sec))
        .where(HourlyActual.date >= month_start, HourlyActual.date <= ref_day)
        .group_by(HourlyActual.user_id)
    )
    talk_by_user = {uid: int(v or 0) for uid, v in talk_rows.all()}

    bonus_rows = list(await db.scalars(select(Bonus).where(Bonus.period == period_key)))
    bonus_by_user = {b.user_id: float(b.amount) for b in bonus_rows}

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

    active = {rid: a for rid, a in current.items() if a["calls"] or a["leads"]}
    if not active:
        return {"text": None, "operators": 0}

    lines: list[str] = []
    changes: list[tuple[str, int]] = []
    for rid, a in sorted(active.items(), key=lambda x: -(x[1]["calls"] + x[1]["leads"])):
        user = user_by_rid.get(rid)
        name = html.escape((user.full_name if user else a["name"]) or str(rid))
        prev = previous.get(rid)
        pct = _pct_change(a["calls"], prev["calls"] if prev else None)
        if pct is not None and rid in user_by_rid:  # "Boshqa" (rid=0) reytingga kirmaydi
            changes.append((name, pct))

        parts = [f"📞 {a['calls']}{_pct_str(pct)}"]
        if user is not None and talk_by_user.get(user.id):
            parts.append(f"🗣 {_fmt_talk(talk_by_user[user.id])}")
        parts.append(f"🧲 {a['leads']}")
        parts.append(f"🏠 {a['visits']}")
        if user is not None and user.id in tasks:
            done, total = tasks[user.id]
            parts.append(f"{'✅' if done == total else '🕓'} {done}/{total}")
        if user is not None and user.id in bonus_by_user:
            parts.append(f"💰 {_fmt_money(bonus_by_user[user.id])}")
        lines.append(f"• <b>{name}</b> — " + " · ".join(parts))

    total_calls = sum(a["calls"] for a in active.values())
    total_leads = sum(a["leads"] for a in active.values())
    total_visits = sum(a["visits"] for a in active.values())
    prev_total_calls = sum(a["calls"] for a in previous.values())
    total_pct = _pct_change(total_calls, prev_total_calls if previous else None)
    active_uids = {user_by_rid[rid].id for rid in active if rid in user_by_rid}
    total_talk = sum(sec for uid, sec in talk_by_user.items() if uid in active_uids)

    totals = f"<b>Jami:</b> 📞 {total_calls}"
    if previous:
        prev_name = MONTH_NAMES_UZ.get(prev_start.month, str(prev_start.month))
        totals += f" ({prev_name.lower()} {prev_total_calls}{_pct_str(total_pct)})"
    if total_talk:
        totals += f" · 🗣 {_fmt_talk(total_talk)}"
    totals += f" · 🧲 {total_leads} · 🏠 {total_visits}"

    month_name = MONTH_NAMES_UZ.get(ref_day.month, period_key)
    parts = [
        f"🗓 <b>Oylik yakun — {month_name} {ref_day.year} ({month_start:%d.%m} – {ref_day:%d.%m})</b>",
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
    if bonus_by_user:
        parts.append(f"💰 Bonuslar jami: {_fmt_money(sum(bonus_by_user.values()))} so'm")
    parts.append("")
    parts.append(
        "<i>📞 qo'ng'iroq (o'tgan oyga nisbatan) · 🗣 gaplashgan vaqt · 🧲 ishlangan lid · "
        "🏠 tashrif · ✅ vazifa · 💰 bonus (hisoblangan bo'lsa)</i>"
    )

    return {"text": "\n".join(parts), "operators": len(active)}


async def send_monthly_digest(db: AsyncSession, chat_id: int | None = None, dry_run: bool = False) -> dict:
    """Oylik digestni quradi va yuboradi. `chat_id` berilmasa — guruh(lar)ga
    (asosiy + statistika guruhlari, daily_digest bilan bir xil nishonlar)."""
    digest = await build_monthly_digest(db)
    if digest["text"] is None:
        return {"sent": False, "reason": "Bu oy uchun ma'lumot topilmadi", "operators": 0}

    if dry_run:
        return {"sent": False, "dry_run": True, "operators": digest["operators"], "text": digest["text"]}

    targets = digest_group_targets(chat_id)
    if not targets:
        return {"sent": False, "reason": "Guruh chat ID sozlanmagan", "operators": digest["operators"]}

    sent_any = False
    for chat in targets:
        ok = await send_message(chat, digest["text"])
        sent_any = sent_any or ok is not None
    return {"sent": sent_any, "operators": digest["operators"], "targets": targets}
