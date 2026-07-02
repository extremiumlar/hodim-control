import httpx

from api.config import settings

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"


async def send_message(chat_id: int, text: str, reply_markup: dict | None = None) -> dict | None:
    """API'dan Telegram'ga chiquvchi xabar yuborish. Token bo'lmasa jim o'tkazib yuboriladi
    (masalan lokal sinovda bot ishga tushirilmagan bo'lishi mumkin)."""
    if not settings.bot_token:
        return None

    url = TELEGRAM_API.format(token=settings.bot_token, method="sendMessage")
    payload: dict = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        payload["reply_markup"] = reply_markup

    async with httpx.AsyncClient(timeout=10) as client:
        try:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError:
            return None


def inline_keyboard(buttons: list[list[tuple[str, str]]]) -> dict:
    """buttons: [[(matn, callback_data), ...], ...]"""
    return {
        "inline_keyboard": [
            [{"text": text, "callback_data": callback_data} for text, callback_data in row]
            for row in buttons
        ]
    }
