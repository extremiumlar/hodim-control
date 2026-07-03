from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot import api_client
from bot.keyboards import BTN_ASSIGN_TASK, main_menu

router = Router(name="assign_task")

ROLE_LABELS = {"employee": "Xodim", "hr": "HR", "rop": "ROP", "boss": "Boshliq"}


class AssignTaskFSM(StatesGroup):
    choosing_target = State()
    entering_title = State()


@router.message(F.text == BTN_ASSIGN_TASK)
async def start_assign_task(message: Message, state: FSMContext) -> None:
    targets = await api_client.assignable_users(message.from_user.id)
    if not targets:
        await message.answer("Sizga vazifa beriladigan foydalanuvchilar topilmadi.")
        return

    buttons = [
        [
            InlineKeyboardButton(
                text=f"{t['full_name']} ({ROLE_LABELS.get(t['role'], t['role'])})",
                callback_data=f"assigntarget:{t['id']}",
            )
        ]
        for t in targets
    ]
    await state.set_state(AssignTaskFSM.choosing_target)
    await message.answer("Kimga vazifa berasiz?", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


@router.callback_query(StateFilter(AssignTaskFSM.choosing_target), F.data.startswith("assigntarget:"))
async def choose_target(callback: CallbackQuery, state: FSMContext) -> None:
    target_id = int(callback.data.split(":")[1])
    await state.update_data(assigned_to=target_id)
    await state.set_state(AssignTaskFSM.entering_title)
    await callback.message.edit_text("Vazifa matnini yozing:")
    await callback.answer()


@router.message(StateFilter(AssignTaskFSM.entering_title))
async def enter_title(message: Message, state: FSMContext) -> None:
    title = message.text.strip()
    if not title:
        await message.answer("Vazifa matnini yozing:")
        return

    data = await state.get_data()
    await state.clear()

    await api_client.bot_create_task(message.from_user.id, data["assigned_to"], title)

    user = await api_client.get_user_by_telegram(message.from_user.id)
    role = user["role"] if user else "employee"
    await message.answer("Vazifa berildi ✅", reply_markup=main_menu(role))
