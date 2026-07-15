from aiogram import Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.types import Message

from bot import api_client
from bot.keyboards import menu_for_user

router = Router(name="start")

ROLE_NAMES = {
    "employee": "Xodim",
    "hr": "HR",
    "rop": "ROP",
    "boss": "Boshliq",
    "dasturchi": "Dasturchi",
}


@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject) -> None:
    invite_token = command.args or None
    result = await api_client.telegram_start(message.from_user.id, invite_token)

    if result["status"] == "invalid_token":
        await message.answer("Havola yaroqsiz yoki muddati o'tgan. Administratorga murojaat qiling.")
        return

    if result["status"] == "no_account":
        await message.answer("Ma'lumotlaringiz hali tizimga kiritilmagan, administratorga murojaat qiling.")
        return

    user = result["user"]
    role_name = ROLE_NAMES.get(user["role"], user["role"])
    position = user.get("position") or {}
    position_line = f"\nLavozim: <b>{position['name']}</b>" if position.get("name") else ""
    await message.answer(
        f"Assalomu alaykum, {user['full_name']}!\n"
        f"Siz tizimga <b>{role_name}</b> sifatida ulandingiz.{position_line}",
        reply_markup=menu_for_user(user),
    )
