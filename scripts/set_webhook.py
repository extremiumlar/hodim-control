"""Telegram webhook'ini o'rnatish yoki o'chirish (cPanel deploy).

Webhook URL: https://<API_DOMEN>/bot/webhook/<BOT_SHARED_SECRET>
API_BASE_URL .env'dan olinadi (masalan https://api.domen.uz).

Ishlatish:
  python scripts/set_webhook.py            # webhook'ni o'rnatadi
  python scripts/set_webhook.py --delete   # webhook'ni o'chiradi (polling'ga qaytish)
  python scripts/set_webhook.py --info      # joriy webhook holatini ko'rsatadi
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aiogram import Bot  # noqa: E402

from bot.config import API_BASE_URL, BOT_SHARED_SECRET, BOT_TOKEN  # noqa: E402
from bot.setup import build_dispatcher  # noqa: E402


async def main() -> None:
    if not BOT_TOKEN:
        sys.exit("BOT_TOKEN sozlanmagan (.env).")
    if not API_BASE_URL.startswith("https://"):
        sys.exit(f"API_BASE_URL HTTPS bo'lishi shart (Telegram webhook talabi): {API_BASE_URL!r}")

    bot = Bot(token=BOT_TOKEN)
    try:
        if "--delete" in sys.argv:
            await bot.delete_webhook(drop_pending_updates=False)
            print("Webhook o'chirildi (polling rejimiga qaytish mumkin).")
            return
        if "--info" in sys.argv:
            info = await bot.get_webhook_info()
            print("URL:", info.url or "(yo'q)")
            print(f"Kutilayotgan update: {info.pending_update_count}")
            if info.last_error_message:
                print(f"Oxirgi xato: {info.last_error_date} — {info.last_error_message}")
            return

        url = f"{API_BASE_URL.rstrip('/')}/bot/webhook/{BOT_SHARED_SECRET}"
        # Dispatcher'dan qaysi update turlari kerakligini olamiz (message_reaction ham)
        dp = build_dispatcher(bot)
        from bot.setup import allowed_update_types

        await bot.set_webhook(
            url=url,
            allowed_updates=allowed_update_types(dp),
            drop_pending_updates=False,
        )
        print(f"Webhook o'rnatildi:\n  {url}")
        print("Endi Telegram update'lari shu manzilga keladi.")
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
