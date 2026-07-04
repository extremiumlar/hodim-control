from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot import api_client
from bot.keyboards import BTN_CANCEL, cancel_menu, menu_for_user

router = Router(name="norms")

METRIC_LABELS = {"suhbat": "Suhbatlar soni", "tashrif": "Tashriflar soni", "video": "Videolar soni"}
DEFAULT_METRICS = ["suhbat", "tashrif"]

# Norma belgilay oladigan rollar: ROP (o'z jamoasi), HR (o'ziga biriktirilgan
# lavozimlar), Boshliq/Dasturchi (hamma) — aniq chegara backendda tekshiriladi.
NORM_MANAGER_ROLES = {"rop", "hr", "boss", "dasturchi"}


class NormFSM(StatesGroup):
    choosing_employee = State()
    choosing_metric = State()
    entering_value = State()


def _metrics_of(emp: dict) -> list[str]:
    """Xodim lavozimiga biriktirilgan ko'rsatkichlar (bo'lmasa standart to'plam)."""
    position = emp.get("position") or {}
    metrics = [m for m in (position.get("metrics") or []) if m in METRIC_LABELS]
    return metrics or DEFAULT_METRICS


@router.message(Command("norma_ozgartir"))
async def cmd_norma_ozgartir(message: Message, state: FSMContext) -> None:
    user = await api_client.get_user_by_telegram(message.from_user.id)
    if not user or user["role"] not in NORM_MANAGER_ROLES:
        await message.answer("Bu buyruq faqat rahbarlar (ROP/HR/Boshliq) uchun mavjud.")
        return

    employees = await api_client.norm_targets(message.from_user.id)
    if not employees:
        await message.answer("Siz norma belgilay oladigan xodimlar topilmadi.")
        return

    # Har bir xodimning lavozim metrikalarini keyingi bosqich uchun saqlab qo'yamiz
    metrics_by_id = {str(emp["id"]): _metrics_of(emp) for emp in employees}
    names_by_id = {str(emp["id"]): emp["full_name"] for emp in employees}
    await state.update_data(metrics_by_id=metrics_by_id, names_by_id=names_by_id)

    buttons = [
        [InlineKeyboardButton(text=emp["full_name"], callback_data=f"normtarget:{emp['id']}")]
        for emp in employees
    ]
    await state.set_state(NormFSM.choosing_employee)
    await message.answer("Kimning normasini o'zgartiramiz?", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


@router.callback_query(StateFilter(NormFSM.choosing_employee), F.data.startswith("normtarget:"))
async def choose_employee(callback: CallbackQuery, state: FSMContext) -> None:
    target_id = callback.data.split(":")[1]
    data = await state.get_data()
    metrics = (data.get("metrics_by_id") or {}).get(target_id, DEFAULT_METRICS)
    name = (data.get("names_by_id") or {}).get(target_id, "?")

    await state.update_data(target_user_id=int(target_id))

    # Faqat shu xodim lavozimida kuzatiladigan ko'rsatkichlar tugma bo'lib chiqadi
    buttons = [
        [InlineKeyboardButton(text=METRIC_LABELS[key], callback_data=f"normmetric:{key}")]
        for key in metrics
    ]

    await state.set_state(NormFSM.choosing_metric)
    await callback.message.edit_text(
        f"{name} uchun qaysi ko'rsatkich?", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await callback.answer()


@router.callback_query(StateFilter(NormFSM.choosing_metric), F.data.startswith("normmetric:"))
async def choose_metric(callback: CallbackQuery, state: FSMContext) -> None:
    metric = callback.data.split(":")[1]
    if metric not in METRIC_LABELS:
        await callback.answer("Noma'lum ko'rsatkich.", show_alert=True)
        return

    await state.update_data(metric_type=metric)
    await state.set_state(NormFSM.entering_value)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        f"{METRIC_LABELS[metric]} uchun yangi qiymatni yozing (butun son):", reply_markup=cancel_menu()
    )
    await callback.answer()


@router.message(StateFilter(NormFSM), F.text == BTN_CANCEL)
async def cancel_norm_change(message: Message, state: FSMContext) -> None:
    await state.clear()
    user = await api_client.get_user_by_telegram(message.from_user.id)
    await message.answer("Bekor qilindi.", reply_markup=menu_for_user(user))


@router.message(StateFilter(NormFSM.entering_value), F.text)
async def enter_value(message: Message, state: FSMContext) -> None:
    try:
        value = int(message.text.strip())
    except ValueError:
        await message.answer("Iltimos, butun son kiriting (masalan: 100).", reply_markup=cancel_menu())
        return

    if value < 0:
        await message.answer("Norma manfiy bo'lishi mumkin emas — 0 yoki undan katta son kiriting.", reply_markup=cancel_menu())
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
    await message.answer(
        f"Norma yangilandi: <b>{METRIC_LABELS.get(data['metric_type'], data['metric_type'])}</b> = {result['value']} "
        f"(kuchga kirish sanasi: {result['effective_from']}).",
        reply_markup=menu_for_user(user),
    )


@router.message(StateFilter(NormFSM.entering_value))
async def non_text_norm_input(message: Message) -> None:
    await message.answer("Iltimos, matn kiriting yoki bekor qiling.", reply_markup=cancel_menu())
