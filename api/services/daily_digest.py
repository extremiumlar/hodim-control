"""Kunlik yagona digest — guruhga BITTA jamlangan xabar.

Ilgari kechqurun guruhga 3 xil oqim alohida-alohida yozardi (vazifalar jadvali,
har operatorga bitta-bitta lid xabari, AI xulosa) — guruh spamga aylanardi. Endi
hammasi shu yerda bitta kompakt xabarga jamlanadi:

  - operator kesimida: qo'ng'iroq (kechaga nisbatan delta), ishlangan lid, tashrif,
    vazifa bajarilishi — bazadagi kunlik snapshotlardan (CRM'ga murojaat yo'q);
  - CRM'da yo'q, lekin bugun vazifa olgan xodimlar (masalan mobilograf) alohida;
  - sababli kunlar va faoliyatsiz xodimlar;
  - jami satri (kechaga nisbatan);
  - AI yoqiq bo'lsa kun yakuni AI xulosasi xabarning OXIRIGA qo'shiladi (alohida
    xabar emas) — matnni `ai_coach.daily_group_summary` yozadi, raqam/soat faktlarini
    esa kod beradi (pasayish epizodlari bilan).

Operator kesimidagi batafsil bosqichlar guruhga chiqmaydi — botdagi "🧲 Lidlar
statistikasi" tugmasida bor."""
import html
from datetime import date, timedelta

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import settings
from api.telegram_notify import send_message
from api.timeutil import local_range_utc_naive, today_local
from db.models import (
    AiConfig,
    ExcusedDay,
    ExcusedStatus,
    HourlyActual,
    LeadStageDaily,
    OperatorCallsDaily,
    Role,
    TaskModel,
    TaskStatus,
    User,
)

# "Tashrif" bosqichi nom bo'yicha (api/routers/stats.py bilan bir xil qoida)
_VISIT_STAGE_NAME = "tashrif"


def digest_group_targets(chat_id: int | None = None) -> list[int]:
    """Statistika digesti yuboriladigan guruh(lar). `chat_id` aniq berilsa (rahbar
    shaxsiy chatda so'raganda) — faqat o'sha. Aks holda: asosiy guruh + statistika
    guruhi (ikkovi ham sozlangan bo'lsa) — digest asosiy guruhda ham, statistika
    guruhida ham chiqadi. Takrorlanmaydigan, nol bo'lmagan ID'lar tartibda."""
    if chat_id:
        return [chat_id]
    targets: list[int] = []
    for cid in (settings.telegram_group_chat_id, *settings.stats_group_ids):
        if cid and cid not in targets:
            targets.append(cid)
    return targets


def _is_visit(stage_name: str) -> bool:
    return stage_name.strip().lower() == _VISIT_STAGE_NAME


def _fmt_talk(sec: int) -> str:
    """Gaplashgan vaqtni ixcham ko'rinishga o'giradi: 5977s → '1s 39d', 1004s → '16d'
    (s=soat, d=daqiqa). Sekundlar tashlanadi — kunlik jami uchun ahamiyatsiz."""
    minutes = sec // 60
    hours, minutes = divmod(minutes, 60)
    return f"{hours}s {minutes}d" if hours else f"{minutes}d"


async def _talk_by_user(db: AsyncSession, day: date) -> dict[int, int]:
    """Har operatorning shu kundagi jami gaplashgan sekundi: {user_id: talk_sec}.
    `HourlyActual` (AI snapshot — CRM call-history sifatidan) dan; javob berilgan
    qo'ng'iroqlar suhbat davomiyligi. Bo'sh bo'lsa (AI o'chiq/snapshot yo'q) — jim."""
    rows = await db.execute(
        select(HourlyActual.user_id, func.sum(HourlyActual.talk_sec))
        .where(HourlyActual.date == day)
        .group_by(HourlyActual.user_id)
    )
    return {uid: int(talk or 0) for uid, talk in rows.all()}


async def _day_by_operator(db: AsyncSession, day: date) -> dict[int, dict]:
    """Bir kunning operator kesimi: {responsible_id: {name, calls, leads, visits}}.
    Lidlar va qo'ng'iroqlar snapshot jadvallaridan (tez, CRM'siz)."""
    agg: dict[int, dict] = {}

    for r in await db.scalars(select(LeadStageDaily).where(LeadStageDaily.date == day)):
        a = agg.setdefault(
            r.responsible_id, {"name": r.responsible_name, "calls": 0, "leads": 0, "visits": 0}
        )
        a["leads"] += r.leads_count
        if _is_visit(r.stage_name):
            a["visits"] += r.leads_count

    for c in await db.scalars(select(OperatorCallsDaily).where(OperatorCallsDaily.date == day)):
        a = agg.setdefault(
            c.responsible_id, {"name": c.responsible_name, "calls": 0, "leads": 0, "visits": 0}
        )
        a["calls"] += c.calls_in + c.calls_out
        if not a.get("name"):
            a["name"] = c.responsible_name

    return agg


async def _tasks_by_user(db: AsyncSession, day: date) -> dict[int, tuple[int, int]]:
    """Bugun berilgan vazifalar: {user_id: (bajarilgan, jami)} — bitta grouped so'rov."""
    day_start, day_end = local_range_utc_naive(day, day)
    rows = await db.execute(
        select(
            TaskModel.assigned_to,
            func.count(TaskModel.id),
            func.sum(case((TaskModel.status == TaskStatus.done.value, 1), else_=0)),
        )
        .where(TaskModel.created_at >= day_start, TaskModel.created_at < day_end)
        .group_by(TaskModel.assigned_to)
    )
    return {uid: (int(done or 0), int(total)) for uid, total, done in rows.all()}


def _delta(today_val: int, yesterday: dict | None) -> str:
    """Kechaga nisbatan farq — kecha ma'lumoti bo'lmasa yoki farq 0 bo'lsa
    ko'rsatilmaydi (shovqin qilmasin)."""
    if yesterday is None:
        return ""
    diff = today_val - yesterday["calls"]
    if diff == 0:
        return ""
    sign = "+" if diff > 0 else ""
    return f" ({sign}{diff})"


async def build_daily_digest(db: AsyncSession, day: date | None = None) -> dict:
    """Digest matnini quradi (yubormaydi). Qaytaradi: {"text", "operators"} —
    bugun umuman faoliyat bo'lmasa text=None."""
    day = day or today_local()
    today_ops = await _day_by_operator(db, day)
    yesterday_ops = await _day_by_operator(db, day - timedelta(days=1))
    tasks = await _tasks_by_user(db, day)
    talk_by_user = await _talk_by_user(db, day)

    employees = list(
        await db.scalars(
            select(User)
            .where(User.role == Role.employee.value, User.is_active == True)  # noqa: E712
            .order_by(User.full_name)
        )
    )
    user_by_rid: dict[int, User] = {}
    for u in employees:
        try:
            if u.crm_visit_external_id:
                user_by_rid[int(u.crm_visit_external_id)] = u
        except (TypeError, ValueError):
            continue

    excused_ids = {
        row
        for row in await db.scalars(
            select(ExcusedDay.user_id).where(
                ExcusedDay.date == day, ExcusedDay.status == ExcusedStatus.approved.value
            )
        )
    }

    def _task_part(user: User | None) -> str:
        if user is None or user.id not in tasks:
            return ""
        done, total = tasks[user.id]
        mark = "✅" if done == total else "🕓"
        return f" · {mark} {done}/{total}"

    def _talk_part(user: User | None) -> str:
        """🗣 gaplashgan vaqt — faqat ma'lumoti bo'lgan operator uchun."""
        if user is None:
            return ""
        sec = talk_by_user.get(user.id, 0)
        return f" · 🗣 {_fmt_talk(sec)}" if sec else ""

    # Operator qatorlari — bugun faoliyati borlar, qo'ng'iroq bo'yicha kamayish tartibida
    active = {rid: a for rid, a in today_ops.items() if a["calls"] or a["leads"]}
    lines: list[str] = []
    for rid, a in sorted(active.items(), key=lambda x: -(x[1]["calls"] + x[1]["leads"])):
        user = user_by_rid.get(rid)
        name = html.escape((user.full_name if user else a["name"]) or str(rid))
        delta = _delta(a["calls"], yesterday_ops.get(rid))
        lines.append(
            f"• <b>{name}</b> — 📞 {a['calls']}{delta}{_talk_part(user)} · "
            f"🧲 {a['leads']} · 🏠 {a['visits']}{_task_part(user)}"
        )

    # CRM faoliyati yo'q, lekin bugun vazifa olgan xodimlar (masalan mobilograf)
    covered_ids = {user_by_rid[rid].id for rid in active if rid in user_by_rid}
    for u in employees:
        if u.id in tasks and u.id not in covered_ids and u.id not in excused_ids:
            done, total = tasks[u.id]
            mark = "✅" if done == total else "🕓"
            lines.append(f"• <b>{html.escape(u.full_name)}</b> — {mark} {done}/{total} vazifa")
            covered_ids.add(u.id)

    if not lines:
        return {"text": None, "operators": 0}

    total_calls = sum(a["calls"] for a in active.values())
    total_leads = sum(a["leads"] for a in active.values())
    total_visits = sum(a["visits"] for a in active.values())
    # Jami gaplashgan vaqt — faqat digestda ko'rsatilgan (faol) operatorlarники
    active_uids = {user_by_rid[rid].id for rid in active if rid in user_by_rid}
    total_talk = sum(sec for uid, sec in talk_by_user.items() if uid in active_uids)
    y_calls = sum(a["calls"] for a in yesterday_ops.values())
    totals = f"<b>Jami:</b> 📞 {total_calls}"
    if yesterday_ops:
        totals += f" (kecha {y_calls})"
    if total_talk:
        totals += f" · 🗣 {_fmt_talk(total_talk)}"
    totals += f" · 🧲 {total_leads} · 🏠 {total_visits}"

    excused_names = [html.escape(u.full_name) for u in employees if u.id in excused_ids]
    idle_names = [
        html.escape(u.full_name)
        for u in employees
        if u.id not in covered_ids and u.id not in excused_ids
    ]

    parts = [f"📊 <b>Kun yakuni — {day:%d.%m.%Y}</b>", "", *lines, "", totals]
    if excused_names:
        parts.append("🙋 Sababli kun: " + ", ".join(excused_names))
    if idle_names:
        parts.append("😴 Bugun faoliyat qayd etilmagan: " + ", ".join(idle_names))
    parts.append("")
    parts.append(
        "<i>📞 qo'ng'iroq (kechaga nisbatan) · 🗣 gaplashgan vaqt (s=soat, d=daqiqa) · "
        "🧲 ishlangan lid · 🏠 tashrif · ✅ vazifa</i>"
    )
    if 0 in active:
        # rid=0 — CRM'da employeeNum'i tizim foydalanuvchisiga bog'lanmagan qo'ng'iroqlar
        # yig'indisi (aniq ro'yxat API logida "CRM ID bog'lanmagan" WARNING'ida).
        parts.append(
            "<i>«Boshqa operatorlar» — CRM ID tizimda bog'lanmagan xodimlar qo'ng'iroqlari</i>"
        )
    parts.append("<i>Operator kesimidagi bosqichlar: botda 🧲 Lidlar statistikasi</i>")

    return {"text": "\n".join(parts), "operators": len(active)}


async def _ai_summary_text(db: AsyncSession) -> str | None:
    """AI kun yakuni xulosasi (yoqiq bo'lsa) — digest oxiriga qo'shish uchun.
    Bosh kalitlar: env AI_ENABLED + AI_NUDGE_ENABLED va runtime group_summary_enabled."""
    if not settings.ai_enabled or not settings.ai_nudge_enabled:
        return None
    cfg = await db.get(AiConfig, 1)
    if cfg is not None and not cfg.group_summary_enabled:
        return None

    from api.routers.ai_coach import group_summary  # circular importdan qochish

    result = await group_summary(db)
    return result.get("text") or None


async def send_daily_digest(db: AsyncSession, chat_id: int | None = None, dry_run: bool = False) -> dict:
    """Digestni quradi va yuboradi. `chat_id` berilmasa — sozlangan umumiy guruhga.
    `dry_run` — yubormasdan matnni qaytaradi (sinov)."""
    digest = await build_daily_digest(db)
    if digest["text"] is None:
        return {"sent": False, "reason": "Bugun uchun ma'lumot topilmadi", "operators": 0}

    text = digest["text"]
    ai_text = await _ai_summary_text(db)
    if ai_text:
        text += f"\n\n🤖 <b>AI xulosa</b>\n{ai_text}"

    if dry_run:
        return {"sent": False, "dry_run": True, "operators": digest["operators"], "text": text}

    targets = digest_group_targets(chat_id)
    if not targets:
        return {"sent": False, "reason": "Guruh chat ID sozlanmagan", "operators": digest["operators"]}

    sent_any = False
    for chat in targets:
        ok = await send_message(chat, text)
        sent_any = sent_any or ok is not None
    return {"sent": sent_any, "operators": digest["operators"], "targets": targets}
