import asyncio
import logging

from bot import api_client
from bot.setup import allowed_update_types, build_bot, build_dispatcher

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main() -> None:
    """Polling rejimi (lokal, Docker/VPS). cPanel webhook rejimi uchun
    api/routers/bot_webhook.py — ikkalasi bot/setup.py'dan bir xil dispatcher
    quradi."""
    bot = build_bot()
    dp = build_dispatcher(bot)

    # drop_pending_updates=False — bot o'chiq paytda kelgan xabarlar restartdan
    # keyin QAYTA ISHLANADI. Bu ataylab: operator AI sabab so'roviga javobni bot
    # o'lik paytda yozsa, xabari yo'qolmasligi shart (jonli holat: Shahnozaning
    # sababi shu tufayli o'qilmay qolgan edi). Eski tugma bosishlari qayta kelsa
    # ham handlerlar upsert/idempotent — zarar qilmaydi.
    await bot.delete_webhook(drop_pending_updates=False)

    try:
        await dp.start_polling(bot, allowed_updates=allowed_update_types(dp))
    finally:
        await api_client.close_client()


if __name__ == "__main__":
    asyncio.run(main())
