from datetime import date

import httpx
from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from bot import api_client
from bot.keyboards import BTN_CANCEL, BTN_EXCUSED, cancel_menu, main_menu

router = Router(name="excused")


class ExcusedDayFSM(StatesGroup):
    waiting_for_reason = State()


@router.message(F.text == BTN_EXCUSED)
async def start_excused_request(message: Message, state: FSMContext) -> None:
    await state.set_state(ExcusedDayFSM.waiting_for_reason)
    await message.answer(
        "Bugungi sababli kun uchun sababni yozib yuboring (masalan: kasallik, oilaviy holat).",
        reply_markup=cancel_menu(),
    )


@router.message(StateFilter(ExcusedDayFSM.waiting_for_reason), F.text == BTN_CANCEL)
async def cancel_excused_request(message: Message, state: FSMContext) -> None:
    await state.clear()
    user = await api_client.get_user_by_telegram(message.from_user.id)
    role = user["role"] if user else "employee"
    await message.answer("Bekor qilindi.", reply_markup=main_menu(role))


@router.message(StateFilter(ExcusedDayFSM.waiting_for_reason))
async def receive_excused_reason(message: Message, state: FSMContext) -> None:
    reason = message.text.strip()
    await state.clear()

    await api_client.create_excused_day(message.from_user.id, date.today().isoformat(), reason)

    user = await api_client.get_user_by_telegram(message.from_user.id)
    role = user["role"] if user else "employee"
    await message.answer(
        "So'rovingiz HR'ga yuborildi, javobini shu yerda kutib turing.",
        reply_markup=main_menu(role),
    )


@router.callback_query(F.data.startswith("excused_decide:"))
async def on_excused_decide(callback: CallbackQuery) -> None:
    _, item_id_str, decision = callback.data.split(":")
    try:
        item = await api_client.decide_excused_day(int(item_id_str), callback.from_user.id, decision)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 403:
            await callback.answer("Bu amal uchun ruxsatingiz yo'q.", show_alert=True)
        else:
            await callback.answer("Xatolik yuz berdi.", show_alert=True)
        return

    verdict = "✅ tasdiqlandi" if item["status"] == "approved" else "❌ rad etildi"
    await callback.message.edit_text(
        f"{item['user_full_name']} — {item['date']} sababli kuni {verdict}."
    )
    await callback.answer("Qaror saqlandi.")
