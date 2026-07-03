import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ErrorEvent

from bot import api_client
from bot.config import BOT_TOKEN
from bot.handlers import assign_task, excused, group_stats, menu, mobilograf, norms, start, tasks

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main() -> None:
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN sozlanmagan. .env faylida BOT_TOKEN qiymatini kiriting.")

    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())

    dp.include_router(start.router)
    dp.include_router(menu.router)
    dp.include_router(tasks.router)
    dp.include_router(excused.router)
    dp.include_router(norms.router)
    dp.include_router(mobilograf.router)
    dp.include_router(assign_task.router)
    dp.include_router(group_stats.router)

    @dp.error()
    async def on_error(event: ErrorEvent) -> None:
        """Har qanday handler ichida ushlanmagan xatolikni tutadi — aks holda bot
        jim qolib, foydalanuvchi hech qanday javob olmasdi (masalan backend
        ishlamay qolganda)."""
        logger.exception("Botda kutilmagan xatolik", exc_info=event.exception)

        update = event.update
        chat_id = None
        if update.message:
            chat_id = update.message.chat.id
        elif update.callback_query and update.callback_query.message:
            chat_id = update.callback_query.message.chat.id

        if chat_id:
            try:
                await bot.send_message(chat_id, "⚠️ Xatolik yuz berdi, birozdan keyin urinib ko'ring.")
            except Exception:
                logger.exception("Foydalanuvchiga xato haqida xabar berib bo'lmadi")

    await bot.delete_webhook(drop_pending_updates=True)

    # message_reaction 2-bosqichda (mobilograf) kerak bo'ladi, lekin uni oldindan
    # yoqib qo'yamiz — aks holda Telegram guruhdagi reaksiyalarni botga umuman yubormaydi.
    allowed_updates = dp.resolve_used_update_types()
    if "message_reaction" not in allowed_updates:
        allowed_updates = [*allowed_updates, "message_reaction"]

    try:
        await dp.start_polling(bot, allowed_updates=allowed_updates)
    finally:
        await api_client.close_client()


if __name__ == "__main__":
    asyncio.run(main())
