from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot import api_client
from bot.keyboards import BTN_ASSIGN_TASK, BTN_CANCEL, cancel_menu, menu_for_user

router = Router(name="assign_task")

ROLE_LABELS = {"employee": "Xodim", "hr": "HR", "rop": "ROP", "boss": "Boshliq", "dasturchi": "Dasturchi"}

# Ommaviy rejim tugmalari (faqat Boshliq/Dasturchi ko'radi) → backend parametrlari
BULK_MODES = {
    "all": {"label": "👥 Barcha xodimlarga", "target_type": "all_employees", "target_roles": None},
    "rops": {"label": "🧭 Barcha ROPlarga", "target_type": "role", "target_roles": ["rop"]},
    "hrs": {"label": "🗂 Barcha HRlarga", "target_type": "role", "target_roles": ["hr"]},
    "rophr": {"label": "🤝 ROP + HR (umumiy)", "target_type": "role", "target_roles": ["rop", "hr"]},
}


class AssignTaskFSM(StatesGroup):
    choosing_mode = State()  # boss/dasturchi: bitta odamga yoki ommaviy
    choosing_target = State()
    entering_title = State()


async def _show_individual_targets(message: Message, state: FSMContext, telegram_id: int) -> bool:
    targets = await api_client.assignable_users(telegram_id)
    if not targets:
        await message.answer("Sizga vazifa beriladigan foydalanuvchilar topilmadi.")
        return False

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
    return True


@router.message(F.text == BTN_ASSIGN_TASK)
async def start_assign_task(message: Message, state: FSMContext) -> None:
    await state.clear()
    user = await api_client.get_user_by_telegram(message.from_user.id)
    if not user:
        return

    if user["role"] in {"boss", "dasturchi"}:
        # Boshliq/Dasturchi: alohida xodimga yoki ommaviy (hammaga/rol bo'yicha/
        # lavozim bo'yicha — backend target_type="position" bilan qo'llaydi)
        buttons = [[InlineKeyboardButton(text="👤 Bitta odamga", callback_data="assignmode:single")]]
        buttons += [
            [InlineKeyboardButton(text=mode["label"], callback_data=f"assignmode:{key}")]
            for key, mode in BULK_MODES.items()
        ]

        positions = await api_client.list_positions()
        buttons += [
            [InlineKeyboardButton(text=f"🏷 Lavozim: {p['name']}", callback_data=f"assignmode:pos_{p['id']}")]
            for p in positions
        ]
        # Lavozim nomlari keyingi bosqichdagi tasdiqlash matni uchun saqlanadi
        await state.update_data(position_names={str(p["id"]): p["name"] for p in positions})

        await state.set_state(AssignTaskFSM.choosing_mode)
        await message.answer(
            "Vazifani kimga berasiz?", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )
        return

    await _show_individual_targets(message, state, message.from_user.id)


@router.callback_query(StateFilter(AssignTaskFSM.choosing_mode), F.data.startswith("assignmode:"))
async def choose_mode(callback: CallbackQuery, state: FSMContext) -> None:
    mode_key = callback.data.split(":")[1]
    await callback.message.edit_reply_markup(reply_markup=None)

    if mode_key == "single":
        shown = await _show_individual_targets(callback.message, state, callback.from_user.id)
        if not shown:
            await state.clear()
        await callback.answer()
        return

    if mode_key.startswith("pos_"):
        position_id = int(mode_key.removeprefix("pos_"))
        data = await state.get_data()
        name = (data.get("position_names") or {}).get(str(position_id), "?")
        await state.update_data(bulk_mode="position", bulk_position_id=position_id)
        await state.set_state(AssignTaskFSM.entering_title)
        await callback.message.answer(
            f"🏷 Lavozim: {name} — vazifa matnini yozing:", reply_markup=cancel_menu()
        )
        await callback.answer()
        return

    mode = BULK_MODES.get(mode_key)
    if not mode:
        await state.clear()
        await callback.answer("Noma'lum tanlov.", show_alert=True)
        return

    await state.update_data(bulk_mode=mode_key)
    await state.set_state(AssignTaskFSM.entering_title)
    await callback.message.answer(
        f"{mode['label']} — vazifa matnini yozing:", reply_markup=cancel_menu()
    )
    await callback.answer()


@router.callback_query(StateFilter(AssignTaskFSM.choosing_target), F.data.startswith("assigntarget:"))
async def choose_target(callback: CallbackQuery, state: FSMContext) -> None:
    target_id = int(callback.data.split(":")[1])
    await state.update_data(assigned_to=target_id, bulk_mode=None)
    await state.set_state(AssignTaskFSM.entering_title)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("Vazifa matnini yozing:", reply_markup=cancel_menu())
    await callback.answer()


@router.message(StateFilter(AssignTaskFSM), F.text == BTN_CANCEL)
async def cancel_assign_task(message: Message, state: FSMContext) -> None:
    await state.clear()
    user = await api_client.get_user_by_telegram(message.from_user.id)
    await message.answer("Bekor qilindi.", reply_markup=menu_for_user(user))


@router.message(StateFilter(AssignTaskFSM.entering_title), F.text)
async def enter_title(message: Message, state: FSMContext) -> None:
    title = message.text.strip()
    if not title:
        await message.answer("Vazifa matnini yozing:", reply_markup=cancel_menu())
        return

    data = await state.get_data()
    await state.clear()

    bulk_mode = data.get("bulk_mode")
    if bulk_mode == "position":
        result = await api_client.bot_create_bulk_tasks(
            assigner_telegram_id=message.from_user.id,
            target_type="position",
            position_id=data["bulk_position_id"],
            title=title,
        )
        confirmation = f"Vazifa {result['created']} kishiga berildi ✅"
    elif bulk_mode:
        mode = BULK_MODES[bulk_mode]
        result = await api_client.bot_create_bulk_tasks(
            assigner_telegram_id=message.from_user.id,
            target_type=mode["target_type"],
            target_roles=mode["target_roles"],
            title=title,
        )
        confirmation = f"Vazifa {result['created']} kishiga berildi ✅"
    else:
        await api_client.bot_create_task(message.from_user.id, data["assigned_to"], title)
        confirmation = "Vazifa berildi ✅"

    user = await api_client.get_user_by_telegram(message.from_user.id)
    await message.answer(confirmation, reply_markup=menu_for_user(user))


@router.message(StateFilter(AssignTaskFSM.entering_title))
async def non_text_task_title(message: Message) -> None:
    await message.answer("Iltimos, matn kiriting yoki bekor qiling.", reply_markup=cancel_menu())
