from aiogram import F, Router
from aiogram.types import Message

from bot import api_client
from bot.keyboards import BTN_GLOBAL_STATS, BTN_MY_STATS, MANAGER_ROLES

router = Router(name="stats")

METRIC_MONTH_LABELS = {"suhbat": "Suhbatlar", "tashrif": "Tashriflar", "video": "Videolar"}


@router.message(F.text == BTN_MY_STATS)
async def show_my_stats(message: Message) -> None:
    """Har bir xodim o'z statistikasini oladi: bugungi holat, oylik jami,
    vazifalar bajarilishi va sababli kunlar."""
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


@router.message(F.text == BTN_GLOBAL_STATS)
async def show_global_stats(message: Message) -> None:
    """Umumiy statistika — faqat HR/ROP/Boshliq/Dasturchi. Kunlik xulosa va
    qo'ng'iroqlar statistikasi so'ralgan chatning o'ziga yuboriladi."""
    user = await api_client.get_user_by_telegram(message.from_user.id)
    if not user or user["role"] not in MANAGER_ROLES:
        return

    summary_result = await api_client.trigger_daily_summary(chat_id=message.chat.id)
    if not summary_result.get("sent"):
        await message.answer("Kunlik xulosani tayyorlab bo'lmadi.")

    call_stats_result = await api_client.trigger_call_stats(chat_id=message.chat.id)
    if not call_stats_result.get("sent"):
        reason = call_stats_result.get("reason")
        if reason and reason != "CRM sozlanmagan":
            await message.answer(f"Qo'ng'iroqlar statistikasi: {reason}")
