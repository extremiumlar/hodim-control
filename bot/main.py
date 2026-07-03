import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from bot.config import BOT_TOKEN
from bot.handlers import assign_task, excused, menu, mobilograf, norms, start, tasks

logging.basicConfig(level=logging.INFO)


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

    await bot.delete_webhook(drop_pending_updates=True)

    # message_reaction 2-bosqichda (mobilograf) kerak bo'ladi, lekin uni oldindan
    # yoqib qo'yamiz — aks holda Telegram guruhdagi reaksiyalarni botga umuman yubormaydi.
    allowed_updates = dp.resolve_used_update_types()
    if "message_reaction" not in allowed_updates:
        allowed_updates = [*allowed_updates, "message_reaction"]

    await dp.start_polling(bot, allowed_updates=allowed_updates)


if __name__ == "__main__":
    asyncio.run(main())
