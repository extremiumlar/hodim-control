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

    # Saytga bot orqali kirish (Telegram Login Widget o'rniga): /start login_<code>
    # — bu ONBOARDING invite_token emas, sayt sessiyasini shu odamga bog'lash.
    if invite_token and invite_token.startswith("login_"):
        code = invite_token.removeprefix("login_")
        result = await api_client.claim_deeplink_login(code, message.from_user.id)
        if result.get("status") == "ok":
            await message.answer(
                "✅ Tasdiqlandi! Saytga qaytib, avtomatik kirishni kuting."
            )
        else:
            await message.answer(
                "⚠️ Kirish havolasi eskirgan yoki noto'g'ri. Saytda sahifani "
                "yangilab qayta urinib ko'ring."
            )
        return

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
