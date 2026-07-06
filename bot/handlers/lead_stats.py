import html
from datetime import date

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot import api_client
from bot.keyboards import BTN_LEAD_STATS

router = Router(name="lead_stats")

MONTH_NAMES = {
    1: "Yanvar", 2: "Fevral", 3: "Mart", 4: "Aprel", 5: "May", 6: "Iyun",
    7: "Iyul", 8: "Avgust", 9: "Sentabr", 10: "Oktabr", 11: "Noyabr", 12: "Dekabr",
}

DAY_BUTTONS_PER_ROW = 7


def _month_title(month_key: str) -> str:
    year, mon = int(month_key[:4]), int(month_key[5:7])
    return f"{MONTH_NAMES.get(mon, month_key)} {year}"


def _month_text(data: dict) -> str:
    lines = [
        f"🧲 <b>Lidlar statistikasi — {_month_title(data['month'])}</b>",
        f"Jami gaplashilgan lidlar: <b>{data['total']}</b> | Tashriflar: <b>{data['visits']}</b>",
    ]
    if data["days"]:
        lines.append("")
        for day_row in data["days"]:
            d = date.fromisoformat(day_row["date"])
            visits_part = f", {day_row['visits']} tashrif" if day_row["visits"] else ""
            lines.append(f"{d:%d.%m} — {day_row['total']} lid{visits_part}")
        lines.append("")
        lines.append("Kun bo'yicha bosqich kesimi uchun sanani tanlang:")
    else:
        lines.append("")
        lines.append("Bu oy uchun hali ma'lumot yo'q.")
    return "\n".join(lines)


def _month_keyboard(data: dict) -> InlineKeyboardMarkup | None:
    """Har bir ma'lumotli kun uchun tugma (7 tadan qatorda) — kalendar ko'rinishida."""
    if not data["days"]:
        return None
    buttons = [
        InlineKeyboardButton(text=str(date.fromisoformat(d["date"]).day), callback_data=f"leadstats:d:{d['date']}")
        for d in data["days"]
    ]
    rows = [buttons[i : i + DAY_BUTTONS_PER_ROW] for i in range(0, len(buttons), DAY_BUTTONS_PER_ROW)]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _day_text(data: dict) -> str:
    d = date.fromisoformat(data["date"])
    lines = [
        f"🧲 <b>Lidlar statistikasi — {d:%d.%m.%Y}</b>",
        f"Umumiy gaplashilgan lidlar: <b>{data['total']}</b>",
    ]
    if data["stages"]:
        # CRM'da bir nechta voronka bo'lishi mumkin va ularda bir xil nomli bosqichlar
        # bor (masalan ikkala voronkada ham "Tashrif") — o'quvchi uchun nom bo'yicha
        # birlashtirib ko'rsatamiz.
        merged: dict[str, int] = {}
        for stage in data["stages"]:
            merged[stage["stage_name"]] = merged.get(stage["stage_name"], 0) + stage["count"]
        lines.append("")
        for name, count in sorted(merged.items(), key=lambda item: -item[1]):
            lines.append(f"• {html.escape(name)}: {count}")
    else:
        lines.append("")
        lines.append("Bu kun uchun ma'lumot yo'q.")
    return "\n".join(lines)


@router.message(F.text == BTN_LEAD_STATS)
async def show_lead_stats(message: Message, state: FSMContext) -> None:
    """Joriy oyning lidlar statistikasi (CRM bosqichlari kesimida): oylik jami,
    har kunning lid/tashrif soni va kun tanlash tugmalari. Ruxsat backendda
    tekshiriladi (sotuv operatorlari va rahbar rollar)."""
    await state.clear()
    waiting = await message.answer("⏳ CRM'dan yangilanmoqda...")
    data = await api_client.lead_stage_month(message.from_user.id)
    if data is None:
        await waiting.edit_text(
            "⛔️ Kechirasiz, lidlar statistikasi faqat sotuv operatorlari va "
            "rahbarlar uchun mavjud. Sizning lavozimingizda bu bo'lim yo'q."
        )
        return
    await waiting.edit_text(_month_text(data), reply_markup=_month_keyboard(data))


@router.callback_query(F.data.startswith("leadstats:d:"))
async def show_lead_stats_day(callback: CallbackQuery) -> None:
    day = callback.data.split(":")[2]
    await callback.answer()
    data = await api_client.lead_stage_day(callback.from_user.id, day)
    if data is None:
        await callback.message.answer(
            "⛔️ Kechirasiz, lidlar statistikasi faqat sotuv operatorlari va "
            "rahbarlar uchun mavjud. Sizning lavozimingizda bu bo'lim yo'q."
        )
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="⬅️ Oyga qaytish", callback_data="leadstats:month")]]
    )
    await callback.message.edit_text(_day_text(data), reply_markup=keyboard)


@router.callback_query(F.data == "leadstats:month")
async def back_to_month(callback: CallbackQuery) -> None:
    await callback.answer()
    data = await api_client.lead_stage_month(callback.from_user.id)
    if data is None:
        return
    await callback.message.edit_text(_month_text(data), reply_markup=_month_keyboard(data))
