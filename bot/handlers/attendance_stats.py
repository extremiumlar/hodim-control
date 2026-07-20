"""«🕐 Davomat statistikasi» — rahbarlar uchun kechikish statistikasi.

Tugma bosilganda shaxsiy chatда statistika chiqadi (default: oxirgi 7 kun);
inline tugmalar bilan davrni almashtirish (Bugun / 7 kun / 30 kun) va
«📤 Guruhga yuborish» — sozlangan umumiy guruhga xuddi shu matnni yuboradi.

Ma'lumot manbai: /attendance/late-stats-bot/{telegram_id} (yagona backend,
kunma-kun late_minutes)."""
import html

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot import api_client
from bot.config import TELEGRAM_GROUP_CHAT_ID
from bot.keyboards import BTN_ATTENDANCE_STATS

router = Router(name="attendance_stats")

PERIODS = [(0, "Bugun"), (7, "7 kun"), (30, "30 kun")]
VALID_DAYS = {d for d, _ in PERIODS}


def _period_title(days: int) -> str:
    return "bugun" if days == 0 else f"oxirgi {days} kun"


def format_late_stats(rows: list[dict], days: int) -> str:
    """Statistika matni (HTML) — DM va guruh uchun bir xil ko'rinish."""
    title = f"🕐 <b>Kechikish statistikasi</b> ({_period_title(days)})"
    if not rows:
        return f"{title}\n\n✅ Hech kim kechikmagan."

    lines = [title, ""]
    for i, r in enumerate(rows, 1):
        lines.append(
            f"{i}. <b>{html.escape(r['full_name'])}</b> — jami <b>{r['total_late_minutes']} daq</b>"
            f" ({r['late_days']} kun, o'rtacha {r['avg_late_minutes']}, eng ko'p {r['max_late_minutes']})"
        )
        # Kunma-kun: "16.07 +20 · 17.07 +15" (sana ISO: YYYY-MM-DD)
        day_bits = " · ".join(
            f"{d['date'][8:10]}.{d['date'][5:7]} +{d['late_minutes']}" for d in r["days"]
        )
        lines.append(f"    {day_bits}")
    lines.append("")
    lines.append(f"Jami kechikkanlar: {len(rows)} xodim")
    return "\n".join(lines)


def _kb(days: int) -> InlineKeyboardMarkup:
    period_row = [
        InlineKeyboardButton(
            text=("✅ " if d == days else "") + label, callback_data=f"attstat:show:{d}"
        )
        for d, label in PERIODS
    ]
    rows = [period_row]
    if TELEGRAM_GROUP_CHAT_ID:
        rows.append(
            [InlineKeyboardButton(text="📤 Guruhga yuborish", callback_data=f"attstat:send:{days}")]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(F.text == BTN_ATTENDANCE_STATS)
async def show_attendance_stats(message: Message, state: FSMContext) -> None:
    await state.clear()  # boshqa menyu tugmalari kabi chala FSM oqimini tozalaydi
    days = 7
    rows = await api_client.attendance_late_stats(message.from_user.id, days)
    if rows is None:
        await message.answer("Bu bo'lim faqat rahbarlar (HR/ROP/Boshliq) uchun.")
        return
    await message.answer(format_late_stats(rows, days), reply_markup=_kb(days))


@router.callback_query(F.data.startswith("attstat:show:"))
async def switch_period(callback: CallbackQuery) -> None:
    try:
        days = int(callback.data.rsplit(":", 1)[1])
    except ValueError:
        await callback.answer()
        return
    if days not in VALID_DAYS:
        await callback.answer()
        return

    rows = await api_client.attendance_late_stats(callback.from_user.id, days)
    if rows is None:
        await callback.answer("Faqat rahbarlar uchun.", show_alert=True)
        return
    try:
        await callback.message.edit_text(format_late_stats(rows, days), reply_markup=_kb(days))
    except Exception:
        # "message is not modified" (bir xil matn) — e'tiborsiz qoldiramiz
        pass
    await callback.answer()


@router.callback_query(F.data.startswith("attstat:send:"))
async def send_to_group(callback: CallbackQuery) -> None:
    try:
        days = int(callback.data.rsplit(":", 1)[1])
    except ValueError:
        await callback.answer()
        return

    rows = await api_client.attendance_late_stats(callback.from_user.id, days)
    if rows is None:
        await callback.answer("Faqat rahbarlar uchun.", show_alert=True)
        return
    if not TELEGRAM_GROUP_CHAT_ID:
        await callback.answer("Guruh sozlanmagan (TELEGRAM_GROUP_CHAT_ID).", show_alert=True)
        return

    try:
        await callback.bot.send_message(TELEGRAM_GROUP_CHAT_ID, format_late_stats(rows, days))
        await callback.answer("✅ Guruhga yuborildi.")
    except Exception:
        await callback.answer("Guruhga yuborib bo'lmadi — bot guruhda bormi?", show_alert=True)
