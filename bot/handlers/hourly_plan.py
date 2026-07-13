from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot import api_client
from bot.keyboards import BTN_HOURLY_PLAN, BTN_HOURLY_PLAN_CONTROL

router = Router()

NO_PLAN = "Bugungi rejani ko'rsatib bo'lmadi (norma yoki jadval sozlanmagan bo'lishi mumkin)."
MANAGER_ROLES = {"hr", "rop", "boss", "dasturchi"}


@router.message(F.text == BTN_HOURLY_PLAN)
async def show_hourly_plan(message: Message, state: FSMContext) -> None:
    """Xodimning bugungi soatma-soat rejasi: kunlik norma ish soatlariga bo'linadi,
    hozirgacha bo'lishi kerak bo'lgan miqdor haqiqiy natija (CRM) bilan solishtiriladi.
    Matn to'liq backendda tayyorlanadi (bot bilan avtomatik eslatma bir xil ko'rinadi)."""
    await state.clear()
    data = await api_client.my_hourly_plan(message.from_user.id)
    if data is None:
        await message.answer(NO_PLAN)
        return
    await message.answer(data["text"])


async def _send_employee_picker(message: Message) -> None:
    """Rahbarga nazoratidagi xodimlar ro'yxatini (inline tugmalar) yuboradi — birini
    tanlagach o'sha xodimning bugungi soatma-soat normasi/rejasi ko'rsatiladi. Inline
    tugmalar guruhda ham ishlaydi, shuning uchun buyruq guruhda ham qo'llanadi."""
    user = await api_client.get_user_by_telegram(message.from_user.id)
    if not user or user["role"] not in MANAGER_ROLES:
        await message.reply("Bu buyruq faqat rahbarlar (ROP/HR/Boshliq) uchun mavjud.")
        return

    employees = await api_client.norm_targets(message.from_user.id)
    if not employees:
        await message.reply("Nazoratingizdagi xodimlar topilmadi.")
        return

    buttons = [
        [InlineKeyboardButton(text=emp["full_name"], callback_data=f"hourlyempl:{emp['id']}")]
        for emp in employees
    ]
    await message.reply(
        "Kimning soatlik normasi/rejasini ko'ramiz?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )


@router.message(F.text == BTN_HOURLY_PLAN_CONTROL)
async def choose_employee_for_plan(message: Message, state: FSMContext) -> None:
    """Rahbar menyu tugmasi orqali: xodim tanlab uning soatma-soat rejasini ko'radi."""
    await state.clear()
    await _send_employee_picker(message)


@router.message(Command("reja"))
async def cmd_reja(message: Message, state: FSMContext) -> None:
    """/reja buyrug'i — "📋 Xodim rejasi" tugmasining buyruq ko'rinishi. Guruhda ham
    ishlaydi (inline piker): rahbar xodim tanlab uning soatlik normasini ko'radi."""
    await state.clear()
    await _send_employee_picker(message)


@router.callback_query(F.data.startswith("hourlyempl:"))
async def show_employee_plan(callback: CallbackQuery) -> None:
    target_id = int(callback.data.split(":")[1])
    data = await api_client.employee_hourly_plan(callback.from_user.id, target_id)
    if data is None:
        await callback.answer("Bu xodim rejasini ko'rish huquqingiz yo'q yoki topilmadi.", show_alert=True)
        return
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(data["text"])
    await callback.answer()
