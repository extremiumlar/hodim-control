from aiogram import Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.types import Message

from bot import api_client
from bot.keyboards import main_menu

router = Router(name="start")

ROLE_NAMES = {
    "employee": "Xodim",
    "hr": "HR",
    "rop": "ROP",
    "boss": "Boshliq",
}


@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject) -> None:
    invite_token = command.args or None
    result = await api_client.telegram_start(message.from_user.id, invite_token)

    if result["status"] == "invalid_token":
        await message.answer("Havola yaroqsiz yoki muddati o'tgan. Administratorga murojaat qiling.")
        return

    if result["status"] == "telegram_already_linked":
        await message.answer(
            "Bu Telegram akkaunt allaqachon boshqa foydalanuvchiga bog'langan. "
            "Avval o'sha foydalanuvchining akkauntini administrator saytdan qayta bog'lashi "
            "(yoki o'chirishi) kerak, so'ng shu havolani qayta bosing."
        )
        return

    if result["status"] == "no_account":
        await message.answer("Ma'lumotlaringiz hali tizimga kiritilmagan, administratorga murojaat qiling.")
        return

    user = result["user"]
    role_name = ROLE_NAMES.get(user["role"], user["role"])
    await message.answer(
        f"Assalomu alaykum, {user['full_name']}!\nSiz tizimga <b>{role_name}</b> sifatida ulandingiz.",
        reply_markup=main_menu(user["role"]),
    )
