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


APP_LOGIN_PREFIX = "applogin_"


async def _handle_app_login(message: Message, login_token: str) -> None:
    """Mobil ilova "Kirish" tugmasi bilan ochilgan deep-link
    (MOBIL_ILOVA_REJASI.md 4.1-band) — oddiy taklif-havola oqimidan alohida,
    chunki bu yerda yangi hisob yaratilmaydi, faqat allaqachon mavjud
    foydalanuvchi ilova sessiyasini tasdiqlaydi."""
    result = await api_client.confirm_app_login(login_token, message.from_user.id)

    if result["status"] == "ok":
        await message.answer("✅ Mobil ilovaga kirish tasdiqlandi. Ilovaga qayting.")
    elif result["status"] == "no_account":
        await message.answer(
            "Sizning hisobingiz topilmadi yoki ilovaga kirish ruxsatingiz yo'q. "
            "Administratorga murojaat qiling."
        )
    else:
        await message.answer("Havola yaroqsiz yoki muddati o'tgan. Ilovada qaytadan urinib ko'ring.")


@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject) -> None:
    invite_token = command.args or None

    if invite_token and invite_token.startswith(APP_LOGIN_PREFIX):
        await _handle_app_login(message, invite_token[len(APP_LOGIN_PREFIX):])
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
