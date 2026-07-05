import html

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot import api_client
from bot.keyboards import BTN_CALC_KPI, BTN_GLOBAL_STATS, BTN_MY_STATS, BTN_TASK_CONTROL, MANAGER_ROLES

router = Router(name="stats")

METRIC_MONTH_LABELS = {"suhbat": "Suhbatlar", "tashrif": "Tashriflar", "video": "Videolar"}


@router.message(F.text == BTN_MY_STATS)
async def show_my_stats(message: Message, state: FSMContext) -> None:
    """Har bir xodim o'z statistikasini oladi: bugungi holat, oylik jami,
    vazifalar bajarilishi va sababli kunlar."""
    # Asosiy menyu tugmasi har doim avvalgi FSM oqimini (masalan chala qolgan
    # norma o'zgartirish) tozalaydi — holat "osilib qolmasligi" uchun.
    await state.clear()
    stats = await api_client.my_stats(message.from_user.id)

    lines = [f"📈 <b>Statistikangiz</b> ({stats['period']})"]

    today_rows = stats.get("today") or []
    if today_rows:
        lines.append("")
        lines.append("<b>Bugun:</b>")
        for m in today_rows:
            norm_part = f"/{m['norm']}" if m.get("norm") is not None else ""
            lines.append(f"  {m['label']}: {m['value']}{norm_part}")

    month_totals = stats.get("month_totals") or {}
    if month_totals:
        lines.append("")
        lines.append("<b>Shu oyda jami:</b>")
        for key, total in month_totals.items():
            lines.append(f"  {METRIC_MONTH_LABELS.get(key, key)}: {total}")

    lines.append("")
    lines.append(f"<b>Vazifalar (shu oy):</b> {stats['tasks_done']}/{stats['tasks_total']} bajarildi")
    if stats.get("excused_days"):
        lines.append(f"<b>Sababli kunlar:</b> {stats['excused_days']} kun")

    await message.answer("\n".join(lines))


@router.message(F.text == BTN_TASK_CONTROL)
async def show_task_control(message: Message, state: FSMContext) -> None:
    """Rahbarlar uchun: bugun berilgan vazifalar — kim bajardi, kim hali yo'q.
    ROP faqat o'z jamoasini ko'radi (qamrov backendda cheklanadi)."""
    await state.clear()
    user = await api_client.get_user_by_telegram(message.from_user.id)
    if not user or user["role"] not in MANAGER_ROLES:
        return

    tasks = await api_client.tasks_overview(message.from_user.id)
    if not tasks:
        await message.answer("Bugun berilgan vazifalar yo'q.")
        return

    done = [t for t in tasks if t["status"] == "done"]
    pending = [t for t in tasks if t["status"] != "done"]

    def _lines(items: list[dict]) -> list[str]:
        return [f"  • {i['assigned_to_name']} — {html.escape(i['title'])}" for i in items[:30]]

    lines = [f"📋 <b>Bugungi vazifalar</b> ({len(done)}/{len(tasks)} bajarildi)"]
    if done:
        lines.append("")
        lines.append("✅ <b>Bajarilgan:</b>")
        lines.extend(_lines(done))
    if pending:
        lines.append("")
        lines.append("🕓 <b>Bajarilmagan:</b>")
        lines.extend(_lines(pending))
    await message.answer("\n".join(lines))


@router.message(F.text == BTN_CALC_KPI)
async def calc_monthly_kpi(message: Message, state: FSMContext) -> None:
    """Faqat Boshliq/Dasturchi: joriy oy KPI/bonusini barcha xodimlar uchun
    darhol qayta hisoblaydi (oy oxirini kutmasdan). Har bir xodimga bot orqali
    "bonus hisoblandi" xabari ketadi."""
    await state.clear()
    user = await api_client.get_user_by_telegram(message.from_user.id)
    if not user or user["role"] not in {"boss", "dasturchi"}:
        return

    result = await api_client.trigger_bonus_calculation()
    await message.answer(
        f"💰 KPI/bonus <b>{result['period']}</b> davri uchun {result['calculated']} xodimga "
        "qayta hisoblandi.\nTafsilotlar saytdagi xodim profillarida (Bonus tarixi)."
    )


async def send_global_stats(message: Message, *, to_group: bool) -> None:
    """Kunlik xulosa + qo'ng'iroqlar statistikasini yuboradi — "📊 Umumiy
    statistika" tugmasi (shaxsiy chatga) va guruhdagi /statistika buyrug'i
    (sozlangan guruhga) uchun umumiy qism; farq faqat nishon chat va
    xato-xabar formatida."""
    chat_id = None if to_group else message.chat.id
    respond = message.reply if to_group else message.answer

    summary_result = await api_client.trigger_daily_summary(chat_id=chat_id)
    if not summary_result.get("sent"):
        await respond(
            "Kunlik xulosani yuborib bo'lmadi — guruh sozlamalarini tekshiring."
            if to_group
            else "Kunlik xulosani tayyorlab bo'lmadi."
        )

    call_stats_result = await api_client.trigger_call_stats(chat_id=chat_id)
    if not call_stats_result.get("sent"):
        reason = call_stats_result.get("reason")
        if to_group:
            reason_text = reason or "CRM ma'lumoti topilmadi"
            await respond(f"Qo'ng'iroqlar statistikasi yuborilmadi: {reason_text}")
        elif reason and reason != "CRM sozlanmagan":
            await respond(f"Qo'ng'iroqlar statistikasi: {reason}")


@router.message(F.text == BTN_GLOBAL_STATS)
async def show_global_stats(message: Message, state: FSMContext) -> None:
    """Umumiy statistika — faqat HR/ROP/Boshliq/Dasturchi. Kunlik xulosa va
    qo'ng'iroqlar statistikasi so'ralgan chatning o'ziga yuboriladi."""
    await state.clear()
    user = await api_client.get_user_by_telegram(message.from_user.id)
    if not user or user["role"] not in MANAGER_ROLES:
        return

    await send_global_stats(message, to_group=False)
