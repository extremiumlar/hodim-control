from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot import api_client
from bot.keyboards import BTN_HOURLY_PLAN

router = Router()

NO_PLAN = "Bugungi rejani ko'rsatib bo'lmadi (norma yoki jadval sozlanmagan bo'lishi mumkin)."


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
