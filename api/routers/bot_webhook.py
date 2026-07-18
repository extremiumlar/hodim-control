"""Telegram webhook qabul qiluvchisi — cPanel (shared hosting) deploy uchun.

Shared hostingda doimiy polling jarayoni yo'q, shuning uchun bot shu API ichida
webhook orqali ishlaydi: Telegram har update'ni /bot/webhook/<secret> ga POST
qiladi, biz uni aiogram Dispatcher'iga uzatamiz. Bot va Dispatcher bir marta
(modul yuklanganda) quriladi — polling bilan bir xil bot/setup.py'dan.

Faqat settings.bot_webhook_enabled=true bo'lganda api/main.py'ga ulanadi
(Docker/VPS'da bot alohida polling qiladi — bu router ulanmaydi va bot/ paketi
import ham qilinmaydi)."""
import logging

from aiogram.types import Update
from fastapi import APIRouter, Request, Response, status

from api.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/bot", tags=["bot"])

# Bot/Dispatcher import vaqtida emas, birinchi so'rovda lazily quriladi — a2wsgi
# ostidagi doimiy event-loop ichida yaratilib, keyingi so'rovlarda qayta ishlatiladi.
_bot = None
_dp = None


def _ensure_bot():
    global _bot, _dp
    if _bot is None:
        from bot import api_client  # lazy: bot/ paketiga bog'liqlik shu yerda
        from bot.setup import build_bot, build_dispatcher
        from api.main import app as api_app
        from api.services.fsm_storage import DbFsmStorage

        # Bot API'ga tarmoq (HTTPS) o'rniga to'g'ridan-to'g'ri shu jarayon ichida
        # murojaat qilsin — sabab: bot/api_client.py'dagi use_in_process_transport
        # docstringi (Passenger yagona ishchi jarayoniga o'z-o'ziga tiqilib qolish).
        api_client.use_in_process_transport(api_app)

        _bot = build_bot()
        # FSM holati bazada — Passenger ishchisi almashganda (idle-kill / bir
        # nechta ishchi) ko'p bosqichli oqimlar (javob tahriri, ma'lumot qo'shish,
        # vaqt kiritish...) uzilib qolmasligi uchun
        _dp = build_dispatcher(_bot, storage=DbFsmStorage())
    return _bot, _dp


@router.post("/webhook/{secret}")
async def telegram_webhook(secret: str, request: Request) -> Response:
    """Telegram update'ini qabul qilib Dispatcher'ga uzatadi. Sekret URL'da —
    Telegram maxsus sarlavha bermaydi, shuning uchun maxfiylik yo'l orqali.
    Har qanday xato ushlanadi: 200 qaytaramiz, aks holda Telegram update'ni
    qayta-qayta yuboraveradi va navbat tiqiladi."""
    if secret != settings.bot_shared_secret:
        return Response(status_code=status.HTTP_403_FORBIDDEN)
    try:
        bot, dp = _ensure_bot()
        data = await request.json()
        update = Update.model_validate(data, context={"bot": bot})
        await dp.feed_update(bot, update)
    except Exception:
        logger.exception("Webhook update ishlashda xatolik")
    # Telegram'ga har doim 200 — muvaffaqiyatli qabul qilindi (qayta yubormasin)
    return Response(status_code=status.HTTP_200_OK)
