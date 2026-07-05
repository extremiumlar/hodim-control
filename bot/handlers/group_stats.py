from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

from bot import api_client
from bot.config import TELEGRAM_GROUP_CHAT_ID
from bot.handlers.stats import send_global_stats

router = Router(name="group_stats")


@router.message(Command("statistika"), F.chat.id == TELEGRAM_GROUP_CHAT_ID)
async def cmd_statistika(message: Message) -> None:
    user = await api_client.get_user_by_telegram(message.from_user.id)
    if not user or user["role"] not in {"hr", "rop", "boss", "dasturchi"}:
        await message.reply("Bu buyruq faqat HR/ROP/Boshliq uchun mavjud.")
        return

    await send_global_stats(message, to_group=True)
