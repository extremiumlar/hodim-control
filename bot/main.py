import asyncio
import logging
import os

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

    # XAVFSIZLIK: bitta BOT_TOKEN bir vaqtda faqat bitta rejimda (polling YOKI
    # webhook) ishlay oladi. Agar hozir Telegram'da FAOL webhook bo'lsa (odatda
    # production/cPanel), bu yerda polling boshlash uni jimgina O'CHIRIB
    # TASHLAYDI — production bot butunlay to'xtab qoladi (adashib `start_all`
    # bosilganda shu sodir bo'lgan). Shuning uchun oldin tekshiramiz va
    # to'xtaymiz — ataylab lokal polling kerak bo'lsa .env'da
    # FORCE_LOCAL_POLLING=true qo'ying (yoki avval scripts/set_webhook.py
    # --delete bilan production webhook'ni ongli ravishda o'chiring).
    info = await bot.get_webhook_info()
    if info.url and os.getenv("FORCE_LOCAL_POLLING") != "true":
        logger.error(
            "TO'XTATILDI: Telegram'da hozir FAOL webhook bor (%s) — bu ehtimol "
            "production server. Shu yerda polling boshlasa, o'sha webhook "
            "o'chib, production bot ishlamay qoladi. Ataylab lokal polling "
            "kerak bo'lsa: .env'da FORCE_LOCAL_POLLING=true qo'ying, YOKI avval "
            "`python scripts/set_webhook.py --delete` bilan production "
            "webhook'ni ongli ravishda o'chiring.",
            info.url,
        )
        await bot.session.close()
        return

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
