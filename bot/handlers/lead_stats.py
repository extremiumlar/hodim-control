import html
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot import api_client
from bot.keyboards import BTN_LEAD_STATS, MANAGER_ROLES

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
        f"📞 Gaplashilgan lidlar: <b>{data['calls']}</b> | 🧲 Ishlangan lidlar: <b>{data['total']}</b> | Tashriflar: <b>{data['visits']}</b>",
    ]
    if data["days"]:
        lines.append("")
        for day_row in data["days"]:
            d = date.fromisoformat(day_row["date"])
            visits_part = f", {day_row['visits']} tashrif" if day_row["visits"] else ""
            lines.append(f"{d:%d.%m} — {day_row['calls']} gaplashildi, {day_row['total']} lid{visits_part}")
        lines.append("")
        lines.append("Kun tafsiloti uchun sanani tanlang:")
    else:
        lines.append("")
        lines.append("Bu oy uchun hali ma'lumot yo'q.")
    lines.append("")
    lines.append(_last_updated_line(data.get("last_updated")))
    return "\n".join(lines)


def _month_keyboard(data: dict, personal: bool = False) -> InlineKeyboardMarkup | None:
    if not data["days"]:
        return None
    prefix = "leadstats:md:" if personal else "leadstats:d:"
    buttons = [
        InlineKeyboardButton(text=str(date.fromisoformat(d["date"]).day), callback_data=f"{prefix}{d['date']}")
        for d in data["days"]
    ]
    rows = [buttons[i : i + DAY_BUTTONS_PER_ROW] for i in range(0, len(buttons), DAY_BUTTONS_PER_ROW)]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _stages_block(data: dict) -> list[str]:
    if not data["stages"]:
        return ["Bu kun uchun ma'lumot yo'q."]
    return [f"• {html.escape(s['stage_name'])}: {s['count']}" for s in data["stages"]]


def _summary_lines(data: dict) -> list[str]:
    return [
        f"📞 Gaplashilgan lidlar: <b>{data['calls']}</b> "
        f"(kiruvchi {data['calls_in']}, chiquvchi {data['calls_out']})",
        f"🧲 Ishlangan lidlar: <b>{data['total']}</b> | Tashriflar: <b>{data['visits']}</b>",
    ]


def _day_text(data: dict) -> str:
    d = date.fromisoformat(data["date"])
    if data.get("responsible_id") is not None:
        name = html.escape(data.get("responsible_name") or "Operator")
        lines = [f"👤 <b>{name} — {d:%d.%m.%Y}</b>", *_summary_lines(data), ""]
        lines.append("<b>Lid bosqichlari:</b>")
        lines.extend(_stages_block(data))
    else:
        lines = [f"🧲 <b>Lidlar statistikasi — {d:%d.%m.%Y}</b>", *_summary_lines(data), ""]
        lines.append("<b>Lid bosqichlari:</b>")
        lines.extend(_stages_block(data))
        if data.get("operators"):
            lines.append("")
            lines.append("👤 Operatorni tanlab, alohida statistikasini ko'ring:")
    lines.append("")
    lines.append(_last_updated_line(data.get("last_updated")))
    return "\n".join(lines)


def _day_keyboard(data: dict, personal: bool = False) -> InlineKeyboardMarkup:
    d = data["date"]
    rows: list[list[InlineKeyboardButton]] = []
    if personal:
        # Xodim: o'z oyi / boshqa kunlar
        rows.append([InlineKeyboardButton(text="📅 Boshqa kunlar", callback_data="leadstats:mmonth")])
    elif data.get("responsible_id") is not None:
        # Rahbar: operator ko'rinishidan kunning umumiysiga qaytish
        rows.append([InlineKeyboardButton(text="⬅️ Kun umumiysi", callback_data=f"leadstats:d:{d}")])
    else:
        for op in data.get("operators", []):
            label = f"{op['responsible_name']} — {op['calls']} gaplashildi, {op['total']} lid"
            rows.append(
                [InlineKeyboardButton(text=label, callback_data=f"leadstats:op:{d}:{op['responsible_id']}")]
            )
        rows.append([InlineKeyboardButton(text="📅 Boshqa kunlar", callback_data="leadstats:month")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


NO_CRM_ID = (
    "Statistikangizni ko'rsatib bo'lmadi — CRM operator ID'ingiz hali sozlanmagan. "
    "Rahbaringizga murojaat qiling."
)


def _default_day(month_data: dict, today_iso: str) -> str:
    """Boshlang'ich kun: bugun ma'lumoti bo'lsa bugun, aks holda eng so'nggi ma'lumotli
    kun (ma'lumot umuman bo'lmasa — baribir bugun, bo'sh ko'rinish bilan)."""
    days = [d["date"] for d in month_data.get("days", [])]
    if today_iso in days:
        return today_iso
    return days[-1] if days else today_iso


@router.message(F.text == BTN_LEAD_STATS)
async def show_lead_stats(message: Message, state: FSMContext) -> None:
    """Lidlar statistikasi. Tugma bosilishi bilan darhol BUGUNGI to'liq kunlik
    statistika chiqadi (oy/kun tanlamasdan). Rahbarlar (HR/ROP/Boshliq/Dasturchi)
    butun tashkilot + operator kesimini ko'radi; sotuv operatorlari faqat O'Z
    statistikasini. Boshqa kunlar/oy — "📅 Boshqa kunlar" tugmasi orqali."""
    await state.clear()
    user = await api_client.get_user_by_telegram(message.from_user.id)
    if not user or not user.get("is_active"):
        await message.answer(NO_PERMISSION)
        return

    today = datetime.now(TASHKENT_TZ).date().isoformat()
    is_manager = user["role"] in MANAGER_ROLES

    # Oylik ma'lumotdan boshlang'ich kunni aniqlaymiz: bugun ma'lumoti bo'lsa bugun,
    # aks holda eng so'nggi ma'lumotli kun (kun boshida bo'sh chiqmasligi uchun).
    month = (
        await api_client.lead_stage_month(message.from_user.id)
        if is_manager
        else await api_client.my_lead_stage_month(message.from_user.id)
    )
    if month is None:
        await message.answer(NO_PERMISSION if is_manager else NO_CRM_ID)
        return
    day_iso = _default_day(month, today)

    if is_manager:
        data = await api_client.lead_stage_day(message.from_user.id, day_iso)
        markup = _day_keyboard(data) if data else None
    else:
        data = await api_client.my_lead_stage_day(message.from_user.id, day_iso)
        markup = _day_keyboard(data, personal=True) if data else None
    if data is None:
        await message.answer(NO_PERMISSION if is_manager else NO_CRM_ID)
        return
    await message.answer(_day_text(data), reply_markup=markup)


# --- Rahbar (tashkilot) oqimi ---


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


# --- Xodim (shaxsiy) oqimi ---


@router.callback_query(F.data.startswith("leadstats:md:"))
async def show_my_lead_stats_day(callback: CallbackQuery) -> None:
    day = callback.data.split(":")[2]
    await callback.answer()
    data = await api_client.my_lead_stage_day(callback.from_user.id, day)
    if data is None:
        await callback.message.answer(NO_CRM_ID)
        return
    await callback.message.edit_text(_day_text(data), reply_markup=_day_keyboard(data, personal=True))


@router.callback_query(F.data == "leadstats:mmonth")
async def back_to_my_month(callback: CallbackQuery) -> None:
    await callback.answer()
    data = await api_client.my_lead_stage_month(callback.from_user.id)
    if data is None:
        return
    await callback.message.edit_text(_month_text(data), reply_markup=_month_keyboard(data, personal=True))
