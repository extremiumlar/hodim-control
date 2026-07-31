"""Telegram webhook qabul qiluvchisi — cPanel (shared hosting) deploy uchun.

Shared hostingda doimiy polling jarayoni yo'q, shuning uchun bot shu API ichida
webhook orqali ishlaydi: Telegram har update'ni /bot/webhook/<secret> ga POST
qiladi, biz uni aiogram Dispatcher'iga uzatamiz. Bot va Dispatcher bir marta
(modul yuklanganda) quriladi — polling bilan bir xil bot/setup.py'dan.

Faqat settings.bot_webhook_enabled=true bo'lganda api/main.py'ga ulanadi
(Docker/VPS'da bot alohida polling qiladi — bu router ulanmaydi va bot/ paketi
import ham qilinmaydi)."""
import asyncio
import hmac
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

# Fon vazifalariga kuchli havola — aks holda GC tugallanmagan taskni yutib
# yuborishi mumkin (asyncio hujjatidagi ma'lum tuzoq).
_bg_tasks: set = set()


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


async def _feed_in_background(bot, dp, update: Update) -> None:
    """Fon vazifasi: dispatcher'ga uzatish. Xato bu yerda ushlanadi — task
    exception hech qayerda yutilib qolmasin."""
    try:
        await dp.feed_update(bot, update)
    except Exception:
        logger.exception("Webhook update ishlashda xatolik (fon)")


async def _handle_update(request: Request) -> Response:
    """Update'ni FON VAZIFASIDA dispatcher'ga uzatadi va 200 ni DARHOL qaytaradi.

    Nega darhol: cPanel'da Passenger'ga ATIGI 1 ta ishchi berilgan. Avval
    `await dp.feed_update(...)` bot ishlovi TUGAGUNCHA (barcha handlerlar +
    har bir Telegram'ga javob yuborish, har biri 0.5-2s tarmoq I/O) shu yagona
    so'rov o'rnini band qilardi — bot faol ishlatilganda sayt so'rovlari
    navbatda qotardi (davriy 25s+ timeout'lar manbalaridan biri). a2wsgi'ning
    doimiy event-loop'i so'rov tugagandan keyin ham yashaydi, shuning uchun
    fon vazifasi bemalol oxirigacha ishlaydi. Polling rejimida aiogram
    update'larni xuddi shunday parallel ishlaydi — semantika bir xil.

    Har qanday holatda 200 — aks holda Telegram update'ni qayta-qayta
    yuboraveradi va navbat tiqiladi."""
    try:
        bot, dp = _ensure_bot()
        data = await request.json()
        update = Update.model_validate(data, context={"bot": bot})
        task = asyncio.create_task(_feed_in_background(bot, dp, update))
        _bg_tasks.add(task)
        task.add_done_callback(_bg_tasks.discard)
    except Exception:
        logger.exception("Webhook update'ni qabul qilishda xatolik")
    return Response(status_code=status.HTTP_200_OK)


@router.post("/webhook")
async def telegram_webhook(request: Request) -> Response:
    """ASOSIY webhook: sekret Telegram'ning `secret_token` mexanizmi orqali
    `X-Telegram-Bot-Api-Secret-Token` SARLAVHASIDA keladi (URL'da emas).

    Nega shunday: URL yo'llari nginx/cPanel `access_log` ga to'liq yoziladi va
    shared hostingda log fayllari boshqa jarayonlarga ham ko'rinishi mumkin —
    sekret yo'lda bo'lsa u yerdan sizib chiqadi va bot qatlamining barcha
    endpointlari ochiladi."""
    token = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not hmac.compare_digest(token, settings.bot_shared_secret):
        return Response(status_code=status.HTTP_403_FORBIDDEN)
    return await _handle_update(request)


@router.post("/webhook/{secret}", deprecated=True)
async def telegram_webhook_legacy(secret: str, request: Request) -> Response:
    """ESKI yo'l (sekret URL'da) — faqat orqaga moslik uchun: deploy paytida
    webhook hali yangi manzilga ko'chirilmagan bo'lsa, botning uzilib qolmasligi
    uchun. `scripts/set_webhook.py --set` ishga tushirilgach bu yo'l ishlatilmaydi
    va uni olib tashlash mumkin."""
    if not hmac.compare_digest(secret, settings.bot_shared_secret):
        return Response(status_code=status.HTTP_403_FORBIDDEN)
    logger.warning(
        "Webhook ESKI yo'l bilan keldi (sekret URL'da). "
        "`python scripts/set_webhook.py --set` bilan yangi manzilga ko'chiring."
    )
    return await _handle_update(request)
