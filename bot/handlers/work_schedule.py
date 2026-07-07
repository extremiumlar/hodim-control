from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot import api_client
from bot.keyboards import BTN_SCHEDULE, MANAGER_ROLES

router = Router()

TASHKENT_TZ = ZoneInfo("Asia/Tashkent")
WEEKDAYS = ["Dush", "Sesh", "Chor", "Pay", "Jum", "Shan", "Yak"]
NO_SCHEDULE = "Ish jadvalini ko'rsatib bo'lmadi (jadval sozlanmagan bo'lishi mumkin)."


def _today() -> date:
    return datetime.now(TASHKENT_TZ).date()


def _week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _fmt_day(day: dict) -> str:
    """Bir kunning qatori: '09:00–18:00' yoki '🌙 dam olish (izoh)' yoki 'belgilanmagan'."""
    if day["source"] == "unset":
        return "belgilanmagan"
    if not day["is_working"]:
        note = f" ({day['note']})" if day.get("note") else ""
        return f"🌙 dam olish{note}"
    times = f"{day['start_time']}–{day['end_time']}"
    note = f" ({day['note']})" if day.get("note") else ""
    return f"{times}{note}"


def _week_text(data: dict, title: str) -> str:
    days = data["days"]
    first = date.fromisoformat(days[0]["date"])
    last = date.fromisoformat(days[-1]["date"])
    lines = [f"🗓 <b>{title}</b> ({first:%d.%m}–{last:%d.%m})", ""]
    today = _today()
    for day in days:
        d = date.fromisoformat(day["date"])
        marker = "▶️ " if d == today else ""
        lines.append(f"{marker}<b>{WEEKDAYS[day['weekday']]} {d:%d.%m}</b> — {_fmt_day(day)}")
    return "\n".join(lines)


def _week_nav(prefix: str, week_start: date) -> InlineKeyboardMarkup:
    prev_ = (week_start - timedelta(days=7)).isoformat()
    next_ = (week_start + timedelta(days=7)).isoformat()
    return InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(text="‹ Oldingi hafta", callback_data=f"{prefix}:{prev_}"),
            InlineKeyboardButton(text="Keyingi hafta ›", callback_data=f"{prefix}:{next_}"),
        ]]
    )


def _roster_text(rows: list[dict], target: date) -> str:
    """Rahbar uchun: tanlangan kunda kim qaysi soatlarda ishlaydi."""
    lines = [f"🗓 <b>Ish jadvali — {target:%d.%m} ({WEEKDAYS[target.weekday()]})</b>", ""]
    for person in rows:
        day = next((x for x in person["days"] if x["date"] == target.isoformat()), None)
        if day is None:
            continue
        if day["source"] == "unset":
            icon, detail = "▫️", "belgilanmagan"
        elif not day["is_working"]:
            note = f" ({day['note']})" if day.get("note") else ""
            icon, detail = "🌙", f"dam olish{note}"
        else:
            note = f" ({day['note']})" if day.get("note") else ""
            icon, detail = "✅", f"{day['start_time']}–{day['end_time']}{note}"
        lines.append(f"{icon} {person['user_full_name']}: {detail}")
    return "\n".join(lines)


def _roster_nav(target: date) -> InlineKeyboardMarkup:
    prev_ = (target - timedelta(days=1)).isoformat()
    next_ = (target + timedelta(days=1)).isoformat()
    return InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(text="‹ Oldingi kun", callback_data=f"wsched:all:{prev_}"),
            InlineKeyboardButton(text="Keyingi kun ›", callback_data=f"wsched:all:{next_}"),
        ]]
    )


@router.message(F.text == BTN_SCHEDULE)
async def show_schedule(message: Message, state: FSMContext) -> None:
    """Ish jadvali. Xodim o'z haftalik jadvalini ko'radi; rahbar tanlangan kunda
    barcha xodimlar jadvalini (kim qachon ishlaydi) ko'radi."""
    await state.clear()
    user = await api_client.get_user_by_telegram(message.from_user.id)
    if not user or not user.get("is_active"):
        await message.answer(NO_SCHEDULE)
        return

    if user["role"] in MANAGER_ROLES:
        today = _today()
        rows = await api_client.all_work_week(message.from_user.id, today.isoformat())
        if rows is None:
            await message.answer(NO_SCHEDULE)
            return
        await message.answer(_roster_text(rows, today), reply_markup=_roster_nav(today))
    else:
        data = await api_client.my_work_week(message.from_user.id, _today().isoformat())
        if data is None:
            await message.answer(NO_SCHEDULE)
            return
        await message.answer(
            _week_text(data, "Ish jadvalim"),
            reply_markup=_week_nav("wsched:me", date.fromisoformat(data["days"][0]["date"])),
        )


@router.callback_query(F.data.startswith("wsched:me:"))
async def nav_my_week(callback: CallbackQuery) -> None:
    start = callback.data.split(":")[2]
    await callback.answer()
    data = await api_client.my_work_week(callback.from_user.id, start)
    if data is None:
        await callback.message.answer(NO_SCHEDULE)
        return
    await callback.message.edit_text(
        _week_text(data, "Ish jadvalim"),
        reply_markup=_week_nav("wsched:me", date.fromisoformat(data["days"][0]["date"])),
    )


@router.callback_query(F.data.startswith("wsched:all:"))
async def nav_roster(callback: CallbackQuery) -> None:
    target = date.fromisoformat(callback.data.split(":")[2])
    await callback.answer()
    rows = await api_client.all_work_week(callback.from_user.id, target.isoformat())
    if rows is None:
        await callback.message.answer(NO_SCHEDULE)
        return
    await callback.message.edit_text(_roster_text(rows, target), reply_markup=_roster_nav(target))
