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


# file_type -> (Telegram metodi, so'rovdagi maydon nomi)
_MEDIA_METHODS = {
    "photo": ("sendPhoto", "photo"),
    "video": ("sendVideo", "video"),
    "animation": ("sendAnimation", "animation"),
}


async def send_file_id(
    chat_id: int,
    file_id: str,
    file_type: str,
    caption: str | None = None,
    reply_markup: dict | None = None,
) -> dict | None:
    """Telegram'da ALLAQACHON mavjud faylni `file_id` bo'yicha qayta yuborish.

    NEGA KERAK (2026-08-13, jonli xato): xodim e'tirozga skrinshot biriktirsa,
    `file_id` bazaga yozilardi-yu, HR ga faqat MATN ketardi — ya'ni ilova
    hech qachon ko'rinmasdi va xodim "rasmni yubordim" deb o'ylab yurardi.

    Fayl BAYTLARI yuborilmaydi: Telegram'ning o'z `file_id` si qayta
    ishlatiladi, shuning uchun so'rov oddiy JSON (`send_message` bilan bir xil
    og'irlikda) va serverda fayl saqlash umuman kerak emas.

    `file_type`: "photo" -> sendPhoto, "video" -> sendVideo,
    "animation" -> sendAnimation (GIF), qolgani -> sendDocument.
    """
    if not settings.bot_token:
        return None

    method, field = _MEDIA_METHODS.get(file_type, ("sendDocument", "document"))
    url = TELEGRAM_API.format(token=settings.bot_token, method=method)
    payload: dict = {"chat_id": chat_id, field: file_id}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    if caption:
        # Telegram caption chegarasi 1024 belgi — uzun murojaat matni bu yerga
        # sig'maydi, shuning uchun qisqartiriladi (to'liq matn alohida
        # xabarda allaqachon ketgan).
        payload["caption"] = caption[:1024]
        payload["parse_mode"] = "HTML"

    async with httpx.AsyncClient(timeout=20) as client:
        try:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError:
            return None


async def edit_reply_markup(chat_id: int, message_id: int, reply_markup: dict) -> dict | None:
    """Yuborilgan xabarning inline tugmalarini yangilaydi (matnga tegmasdan).

    Tabrik postidagi «👏 Tabriklash (N)» sanog'i shu orqali o'sadi — video
    qayta yuborilmaydi, faqat tugma almashadi."""
    if not settings.bot_token:
        return None

    url = TELEGRAM_API.format(token=settings.bot_token, method="editMessageReplyMarkup")
    payload = {"chat_id": chat_id, "message_id": message_id, "reply_markup": reply_markup}
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


def inline_url_keyboard(buttons: list[list[tuple[str, str]]]) -> dict:
    """buttons: [[(matn, url), ...], ...] — havola ochadigan tugmalar.

    Eslatma xabarlarida «Keldim»ni BOSADIGAN joy bo'lishi shart (UX2-W4):
    ilgari xabar «Keldim ni bosing» der, tugma esa yo'q edi."""
    return {
        "inline_keyboard": [
            [{"text": text, "url": url} for text, url in row] for row in buttons
        ]
    }
