import html

from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot import api_client
from bot.keyboards import BTN_CANCEL, cancel_menu, main_menu

router = Router(name="norms")

METRIC_LABELS = {"suhbat": "Suhbatlar soni", "tashrif": "Tashriflar soni"}


class NormFSM(StatesGroup):
    choosing_employee = State()
    choosing_metric = State()
    entering_custom_metric = State()
    entering_value = State()


@router.message(Command("norma_ozgartir"))
async def cmd_norma_ozgartir(message: Message, state: FSMContext) -> None:
    user = await api_client.get_user_by_telegram(message.from_user.id)
    if not user or user["role"] not in {"rop", "boss"}:
        await message.answer("Bu buyruq faqat ROP/Boshliq uchun mavjud.")
        return

    employees = await api_client.list_employees()
    if not employees:
        await message.answer("Hozircha xodimlar ro'yxati bo'sh.")
        return

    buttons = [
        [InlineKeyboardButton(text=emp["full_name"], callback_data=f"normtarget:{emp['id']}")]
        for emp in employees
    ]
    await state.set_state(NormFSM.choosing_employee)
    await message.answer("Kimning normasini o'zgartiramiz?", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


@router.callback_query(StateFilter(NormFSM.choosing_employee), F.data.startswith("normtarget:"))
async def choose_employee(callback: CallbackQuery, state: FSMContext) -> None:
    target_id = int(callback.data.split(":")[1])
    await state.update_data(target_user_id=target_id)

    buttons = [
        [InlineKeyboardButton(text=label, callback_data=f"normmetric:{key}")]
        for key, label in METRIC_LABELS.items()
    ]
    buttons.append([InlineKeyboardButton(text="Boshqa ko'rsatkich...", callback_data="normmetric:custom")])

    await state.set_state(NormFSM.choosing_metric)
    await callback.message.edit_text(
        "Qaysi ko'rsatkich?", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await callback.answer()


@router.callback_query(StateFilter(NormFSM.choosing_metric), F.data.startswith("normmetric:"))
async def choose_metric(callback: CallbackQuery, state: FSMContext) -> None:
    metric = callback.data.split(":")[1]

    if metric == "custom":
        await state.set_state(NormFSM.entering_custom_metric)
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer(
            "Ko'rsatkich nomini yozing (masalan: sifat_bahosi):", reply_markup=cancel_menu()
        )
        await callback.answer()
        return

    await state.update_data(metric_type=metric)
    await state.set_state(NormFSM.entering_value)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        f"{METRIC_LABELS[metric]} uchun yangi qiymatni yozing (butun son):", reply_markup=cancel_menu()
    )
    await callback.answer()


@router.message(StateFilter(NormFSM.entering_custom_metric, NormFSM.entering_value), F.text == BTN_CANCEL)
async def cancel_norm_change(message: Message, state: FSMContext) -> None:
    await state.clear()
    user = await api_client.get_user_by_telegram(message.from_user.id)
    role = user["role"] if user else "employee"
    await message.answer("Bekor qilindi.", reply_markup=main_menu(role))


@router.message(StateFilter(NormFSM.entering_custom_metric), F.text)
async def enter_custom_metric(message: Message, state: FSMContext) -> None:
    metric = message.text.strip()
    if not metric:
        await message.answer("Ko'rsatkich nomini yozing:", reply_markup=cancel_menu())
        return

    await state.update_data(metric_type=metric)
    await state.set_state(NormFSM.entering_value)
    await message.answer(
        f"'{html.escape(metric)}' uchun yangi qiymatni yozing (butun son):", reply_markup=cancel_menu()
    )


@router.message(StateFilter(NormFSM.entering_value), F.text)
async def enter_value(message: Message, state: FSMContext) -> None:
    try:
        value = int(message.text.strip())
    except ValueError:
        await message.answer("Iltimos, butun son kiriting (masalan: 100).", reply_markup=cancel_menu())
        return

    data = await state.get_data()
    await state.clear()

    result = await api_client.update_norm(
        changer_telegram_id=message.from_user.id,
        target_user_id=data["target_user_id"],
        metric_type=data["metric_type"],
        value=value,
    )
    user = await api_client.get_user_by_telegram(message.from_user.id)
    role = user["role"] if user else "employee"
    await message.answer(
        f"Norma yangilandi: <b>{html.escape(data['metric_type'])}</b> = {result['value']} "
        f"(kuchga kirish sanasi: {result['effective_from']}).",
        reply_markup=main_menu(role),
    )


@router.message(StateFilter(NormFSM.entering_custom_metric, NormFSM.entering_value))
async def non_text_norm_input(message: Message) -> None:
    await message.answer("Iltimos, matn kiriting yoki bekor qiling.", reply_markup=cancel_menu())
