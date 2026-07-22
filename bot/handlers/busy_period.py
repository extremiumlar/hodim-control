"""Boshliq/Dasturchi operator/managerni vaqtincha "band" deb belgilaydi (yig'ilish,
vazifa va h.k.) — shu vaqt davomida real-vaqtli harakatsizlik ogohlantirishi
(idle_watch) o'sha odamga kelmaydi. Vazifa berish (assign_task.py) bilan bir xil
FSM naqshi: nishonni tanlash → davomiylik → ixtiyoriy sabab."""
from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot import api_client
from bot.keyboards import BTN_CANCEL, BTN_SET_BUSY, cancel_menu, menu_for_user

router = Router(name="busy_period")

_DURATION_PRESETS = [("30 daqiqa", 30), ("1 soat", 60), ("2 soat", 120), ("Kun oxirigacha (8 soat)", 480)]


class BusyPeriodFSM(StatesGroup):
    choosing_target = State()
    choosing_duration = State()
    entering_reason = State()


@router.message(F.text == BTN_SET_BUSY)
async def start_busy_period(message: Message, state: FSMContext) -> None:
    await state.clear()
    user = await api_client.get_user_by_telegram(message.from_user.id)
    if not user or user.get("role") not in ("boss", "dasturchi"):
        return

    targets = await api_client.assignable_users(message.from_user.id)
    if not targets:
        await message.answer("Band qilinadigan xodimlar topilmadi.")
        return

    buttons = [
        [InlineKeyboardButton(text=t["full_name"], callback_data=f"busytarget:{t['id']}")] for t in targets
    ]
    await state.set_state(BusyPeriodFSM.choosing_target)
    await message.answer(
        "Kimni band qilib qo'yasiz? (shu vaqt davomida 'nega ishlamayapsiz' xabari kelmaydi)",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )


@router.callback_query(StateFilter(BusyPeriodFSM.choosing_target), F.data.startswith("busytarget:"))
async def choose_target(callback: CallbackQuery, state: FSMContext) -> None:
    target_id = int(callback.data.split(":")[1])
    await state.update_data(target_user_id=target_id)
    await state.set_state(BusyPeriodFSM.choosing_duration)
    await callback.message.edit_reply_markup(reply_markup=None)

    buttons = [
        [InlineKeyboardButton(text=label, callback_data=f"busydur:{minutes}")]
        for label, minutes in _DURATION_PRESETS
    ]
    await callback.message.answer(
        "Qancha vaqtga band?", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await callback.answer()


@router.callback_query(StateFilter(BusyPeriodFSM.choosing_duration), F.data.startswith("busydur:"))
async def choose_duration(callback: CallbackQuery, state: FSMContext) -> None:
    minutes = int(callback.data.split(":")[1])
    await state.update_data(minutes=minutes)
    await state.set_state(BusyPeriodFSM.entering_reason)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        "Sababini yozing (ixtiyoriy — masalan 'Yig'ilishda'), yoki shunchaki '-' deb yuboring:",
        reply_markup=cancel_menu(),
    )
    await callback.answer()


@router.message(StateFilter(BusyPeriodFSM.entering_reason), F.text)
async def enter_reason(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await state.clear()

    reason = message.text.strip()
    if reason in ("-", ""):
        reason = None

    result = await api_client.set_busy_period(
        setter_telegram_id=message.from_user.id,
        target_user_id=data["target_user_id"],
        minutes=data["minutes"],
        reason=reason,
    )
    user = await api_client.get_user_by_telegram(message.from_user.id)
    await message.answer(
        f"✅ <b>{result['target']}</b> band deb belgilandi — {result['minutes']} daqiqaga "
        "(shu vaqt davomida harakatsizlik ogohlantirishi kelmaydi).",
        reply_markup=menu_for_user(user),
    )


@router.message(StateFilter(BusyPeriodFSM), F.text == BTN_CANCEL)
async def cancel_busy_period(message: Message, state: FSMContext) -> None:
    await state.clear()
    user = await api_client.get_user_by_telegram(message.from_user.id)
    await message.answer("Bekor qilindi.", reply_markup=menu_for_user(user))
