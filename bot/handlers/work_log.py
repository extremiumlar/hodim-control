"""Ish kundaligi — botdan yozuv qo'shish (KUNDALIK_ETIROZ_REJASI.md, Bosqich 2).

Oqim: «📝 Ish kundaligi» → bugungi yozuvlar ro'yxati + «➕ Yozuv qo'shish» →
matn → saqlandi → yana qo'shish taklifi.

Tahrirlash/o'chirish botda YO'Q — u xodim kabinetida (Bosqich 3). Bu yerda
ataylab faqat qo'shish: kundalikning qiymati vaqt tamg'asida, botdan tez
yozib qo'yish esa asosiy stsenariy.
"""
import html
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import httpx
from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot import api_client
from bot.keyboards import ALL_MENU_BUTTONS, BTN_CANCEL, BTN_WORK_LOG, cancel_menu, menu_for_user

router = Router(name="work_log")

TASHKENT_TZ = ZoneInfo("Asia/Tashkent")

MIN_LEN = 3
MAX_LEN = 2000


class WorkLogFSM(StatesGroup):
    waiting_text = State()


def _local_hm(iso: str) -> str:
    """Bazadagi naive-UTC vaqt → mahalliy "HH:MM" (lead_stats.py naqshi)."""
    try:
        return f"{datetime.fromisoformat(iso).replace(tzinfo=timezone.utc).astimezone(TASHKENT_TZ):%H:%M}"
    except (TypeError, ValueError):
        return "--:--"


def _add_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="➕ Yozuv qo'shish", callback_data="worklog:add")]]
    )


def _today_text(entries: list) -> str:
    today = f"{datetime.now(TASHKENT_TZ):%d.%m.%Y}"
    if not entries:
        return (
            f"📝 <b>Ish kundaligi — {today}</b>\n\n"
            "Bugun hali yozuv yo'q. Bajargan ishlaringizni qisqacha yozib qo'ying — "
            "kun davomida bir necha marta qo'shsangiz bo'ladi."
        )
    lines = [f"📝 <b>Ish kundaligi — {today}</b>", "", f"Bugungi yozuvlaringiz ({len(entries)}):"]
    for i, e in enumerate(entries, 1):
        lines.append(f"{i}. <i>{_local_hm(e['created_at'])}</i> — {html.escape(e['text'])}")
    lines.append("")
    lines.append("Yana ish bajarsangiz — yangi yozuv qo'shing.")
    return "\n".join(lines)


async def _show_today(message: Message) -> None:
    entries = await api_client.work_log_today(message.from_user.id)
    if entries is None:
        # 404 — ro'yxatdan o'tmagan yoki o'chirilgan xodim (get_user_by_telegram naqshi)
        await message.answer(
            "Siz tizimda ro'yxatdan o'tmagansiz. Rahbaringizdan taklif havolasini so'rang."
        )
        return
    await message.answer(_today_text(entries), reply_markup=_add_kb())


@router.message(F.text == BTN_WORK_LOG)
async def show_work_log(message: Message, state: FSMContext) -> None:
    # Menyu tugmasi — chala qolgan FSM oqimini tozalaydi (menu.py qoidasi).
    await state.clear()
    await _show_today(message)


@router.callback_query(F.data == "worklog:add")
async def start_add_entry(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(WorkLogFSM.waiting_text)
    await callback.message.answer(
        "Bugun nima qildingiz? Qisqacha yozib yuboring "
        "(masalan: «14 ta lid bilan gaplashdim», «3 ta ko'rsatuvga chiqdim»).",
        reply_markup=cancel_menu(),
    )
    await callback.answer()


@router.message(StateFilter(WorkLogFSM.waiting_text), F.text == BTN_CANCEL)
async def cancel_add_entry(message: Message, state: FSMContext) -> None:
    await state.clear()
    user = await api_client.get_user_by_telegram(message.from_user.id)
    await message.answer("Bekor qilindi.", reply_markup=menu_for_user(user))


@router.message(StateFilter(WorkLogFSM.waiting_text), F.text, ~F.text.in_(ALL_MENU_BUTTONS))
async def receive_entry_text(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if len(text) < MIN_LEN:
        # Holat SAQLANADI — xodim qayta yozsin (excused.py:153-156 naqshi).
        await message.answer("Juda qisqa — bajargan ishingizni to'liqroq yozing.", reply_markup=cancel_menu())
        return
    if len(text) > MAX_LEN:
        await message.answer(
            f"Juda uzun ({len(text)} belgi). Ko'pi bilan {MAX_LEN} belgi — "
            "qisqartiring yoki bir nechta yozuvga bo'ling.",
            reply_markup=cancel_menu(),
        )
        return

    await state.clear()
    user = await api_client.get_user_by_telegram(message.from_user.id)
    try:
        await api_client.work_log_add(message.from_user.id, text)
    except httpx.HTTPStatusError as exc:
        detail = "Xatolik yuz berdi."
        try:
            detail = exc.response.json().get("detail", detail)
        except Exception:
            pass
        await message.answer(f"⚠️ {detail}", reply_markup=menu_for_user(user))
        return
    except Exception:
        await message.answer(
            "⚠️ Xatolik yuz berdi. Birozdan so'ng qayta urinib ko'ring.",
            reply_markup=menu_for_user(user),
        )
        return

    entries = await api_client.work_log_today(message.from_user.id) or []
    await message.answer(
        f"✅ Saqlandi (bugun {len(entries)}-yozuv).",
        reply_markup=menu_for_user(user),
    )
    # Ro'yxatni qayta ko'rsatamiz — «yana qo'shish» tugmasi bilan birga,
    # xodim menyuga qaytmasdan navbatdagi ishni yozib qo'ya olsin.
    await message.answer(_today_text(entries), reply_markup=_add_kb())


@router.message(StateFilter(WorkLogFSM.waiting_text), ~F.text)
async def non_text_entry(message: Message) -> None:
    # ~F.text — rasm/stiker; menyu tugmasi matni bu yerda YUTILMAYDI (C3).
    await message.answer("Iltimos, matn kiriting yoki bekor qiling.", reply_markup=cancel_menu())
