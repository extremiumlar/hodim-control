from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

from bot import api_client
from bot.config import TELEGRAM_GROUP_CHAT_ID

router = Router(name="group_stats")


@router.message(Command("statistika"), F.chat.id == TELEGRAM_GROUP_CHAT_ID)
async def cmd_statistika(message: Message) -> None:
    user = await api_client.get_user_by_telegram(message.from_user.id)
    if not user or user["role"] not in {"hr", "rop", "boss", "dasturchi"}:
        await message.reply("Bu buyruq faqat HR/ROP/Boshliq uchun mavjud.")
        return

    summary_result = await api_client.trigger_daily_summary()
    if not summary_result.get("sent"):
        await message.reply("Kunlik xulosani yuborib bo'lmadi — guruh sozlamalarini tekshiring.")

    call_stats_result = await api_client.trigger_call_stats()
    if not call_stats_result.get("sent"):
        reason = call_stats_result.get("reason", "CRM ma'lumoti topilmadi")
        await message.reply(f"Qo'ng'iroqlar statistikasi yuborilmadi: {reason}")
