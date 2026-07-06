import html
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot import api_client
from bot.keyboards import BTN_LEAD_STATS

router = Router(name="lead_stats")

TASHKENT_TZ = ZoneInfo("Asia/Tashkent")

MONTH_NAMES = {
    1: "Yanvar", 2: "Fevral", 3: "Mart", 4: "Aprel", 5: "May", 6: "Iyun",
    7: "Iyul", 8: "Avgust", 9: "Sentabr", 10: "Oktabr", 11: "Noyabr", 12: "Dekabr",
}

DAY_BUTTONS_PER_ROW = 7
OPERATOR_BUTTONS_PER_ROW = 1

NO_PERMISSION = (
    "⛔️ Kechirasiz, lidlar statistikasi faqat sotuv operatorlari va "
    "rahbarlar uchun mavjud. Sizning lavozimingizda bu bo'lim yo'q."
)


def _month_title(month_key: str) -> str:
    year, mon = int(month_key[:4]), int(month_key[5:7])
    return f"{MONTH_NAMES.get(mon, month_key)} {year}"


def _last_updated_line(iso: str | None) -> str:
    """Snapshot oxirgi yangilangan vaqti (bazada naive-UTC) — Toshkentga o'girib
    ko'rsatamiz. Ma'lumot fon rejimida yig'ilgani uchun 'jonli' emasligini bildiradi."""
    if not iso:
        return "ℹ️ Ma'lumot hali yig'ilmagan (fon yangilanishini kuting)."
    dt = datetime.fromisoformat(iso).replace(tzinfo=timezone.utc).astimezone(TASHKENT_TZ)
    return f"🕐 Oxirgi yangilanish: {dt:%d.%m %H:%M}"


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
        lines.append("Kun tafsiloti uchun sanani tanlang:")
    else:
        lines.append("")
        lines.append("Bu oy uchun hali ma'lumot yo'q.")
    lines.append("")
    lines.append(_last_updated_line(data.get("last_updated")))
    return "\n".join(lines)


def _month_keyboard(data: dict) -> InlineKeyboardMarkup | None:
    if not data["days"]:
        return None
    buttons = [
        InlineKeyboardButton(text=str(date.fromisoformat(d["date"]).day), callback_data=f"leadstats:d:{d['date']}")
        for d in data["days"]
    ]
    rows = [buttons[i : i + DAY_BUTTONS_PER_ROW] for i in range(0, len(buttons), DAY_BUTTONS_PER_ROW)]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _stages_block(data: dict) -> list[str]:
    if not data["stages"]:
        return ["Bu kun uchun ma'lumot yo'q."]
    return [f"• {html.escape(s['stage_name'])}: {s['count']}" for s in data["stages"]]


def _day_text(data: dict) -> str:
    d = date.fromisoformat(data["date"])
    if data.get("responsible_id") is not None:
        # Bitta operator ko'rinishi
        name = html.escape(data.get("responsible_name") or "Operator")
        lines = [
            f"🧲 <b>{name} — {d:%d.%m.%Y}</b>",
            f"Umumiy gaplashilgan lidlar: <b>{data['total']}</b> | Tashriflar: <b>{data['visits']}</b>",
            "",
        ]
        lines.extend(_stages_block(data))
    else:
        # Tashkilot jami
        lines = [
            f"🧲 <b>Lidlar statistikasi — {d:%d.%m.%Y}</b>",
            f"Umumiy gaplashilgan lidlar: <b>{data['total']}</b> | Tashriflar: <b>{data['visits']}</b>",
            "",
        ]
        lines.extend(_stages_block(data))
        if data.get("operators"):
            lines.append("")
            lines.append("👤 Operatorni tanlab, alohida statistikasini ko'ring:")
    lines.append("")
    lines.append(_last_updated_line(data.get("last_updated")))
    return "\n".join(lines)


def _day_keyboard(data: dict) -> InlineKeyboardMarkup:
    d = data["date"]
    rows: list[list[InlineKeyboardButton]] = []
    if data.get("responsible_id") is not None:
        # Operator ko'rinishida — kunning umumiysiga qaytish
        rows.append([InlineKeyboardButton(text="⬅️ Kun umumiysi", callback_data=f"leadstats:d:{d}")])
    else:
        for op in data.get("operators", []):
            label = f"{op['responsible_name']} — {op['total']} lid"
            rows.append(
                [InlineKeyboardButton(text=label, callback_data=f"leadstats:op:{d}:{op['responsible_id']}")]
            )
        rows.append([InlineKeyboardButton(text="⬅️ Oyga qaytish", callback_data="leadstats:month")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(F.text == BTN_LEAD_STATS)
async def show_lead_stats(message: Message, state: FSMContext) -> None:
    """Joriy oyning lidlar statistikasi (fon snapshotdan): oylik jami, har kunning
    lid/tashrif soni va kun tanlash tugmalari. Ruxsat backendda tekshiriladi."""
    await state.clear()
    data = await api_client.lead_stage_month(message.from_user.id)
    if data is None:
        await message.answer(NO_PERMISSION)
        return
    await message.answer(_month_text(data), reply_markup=_month_keyboard(data))


@router.callback_query(F.data.startswith("leadstats:d:"))
async def show_lead_stats_day(callback: CallbackQuery) -> None:
    day = callback.data.split(":")[2]
    await callback.answer()
    data = await api_client.lead_stage_day(callback.from_user.id, day)
    if data is None:
        await callback.message.answer(NO_PERMISSION)
        return
    await callback.message.edit_text(_day_text(data), reply_markup=_day_keyboard(data))


@router.callback_query(F.data.startswith("leadstats:op:"))
async def show_lead_stats_operator(callback: CallbackQuery) -> None:
    _, _, day, responsible_id = callback.data.split(":")
    await callback.answer()
    data = await api_client.lead_stage_day(callback.from_user.id, day, responsible_id=int(responsible_id))
    if data is None:
        await callback.message.answer(NO_PERMISSION)
        return
    await callback.message.edit_text(_day_text(data), reply_markup=_day_keyboard(data))


@router.callback_query(F.data == "leadstats:month")
async def back_to_month(callback: CallbackQuery) -> None:
    await callback.answer()
    data = await api_client.lead_stage_month(callback.from_user.id)
    if data is None:
        return
    await callback.message.edit_text(_month_text(data), reply_markup=_month_keyboard(data))
