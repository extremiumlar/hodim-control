"""Bot va Dispatcher qurish — polling (bot/main.py) va webhook (cPanel deploy,
api/routers/bot_webhook.py) UCHUN YAGONA manba. Router tartibi va xato ushlagichi
ikkala rejimda bir xil bo'lishi uchun shu yerda markazlashtirilgan."""
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ErrorEvent

from bot.config import BOT_TOKEN
from bot.handlers import (
    admin_override,
    ai_center,
    ai_watch,
    anketa,
    assign_task,
    attendance_stats,
    busy_period,
    knowledge,
    excused,
    group_admin,
    group_stats,
    hot_lead,
    hourly_plan,
    lead_stats,
    menu,
    mobilograf,
    norms,
    payroll,
    playbook,
    sales_ai,
    start,
    stats,
    tasks,
    work_log,
    work_schedule,
)

logger = logging.getLogger(__name__)


def build_bot() -> Bot:
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN sozlanmagan. .env faylida BOT_TOKEN qiymatini kiriting.")
    return Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))


async def setup_bot_commands(bot: Bot) -> None:
    """UX2-W4 (C8): Telegram'ning "/" menyusi — ilgari umuman sozlanmagan edi,
    /davomat_vaqt kabi buyruqlar faqat hujjatdan bilinardi. Polling'da
    dp.startup orqali, webhook'da scripts/set_webhook.py orqali chaqiriladi
    (ikkalasida ham bir marta yetadi — Telegram saqlab qoladi)."""
    from aiogram.types import BotCommand

    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Bosh menyu"),
            BotCommand(command="statistika", description="Kunlik digest (guruhda, rahbar)"),
            BotCommand(command="davomat_vaqt", description="Davomat digesti vaqti (rahbar)"),
            BotCommand(command="guruhlar", description="Bot guruhlari ro'yxati (rahbar)"),
        ]
    )


def build_dispatcher(bot: Bot, storage=None) -> Dispatcher:
    """`storage` berilmasa MemoryStorage (polling — bitta doimiy jarayon).
    cPanel webhook rejimida api/routers/bot_webhook.py bazaviy storage beradi —
    Passenger ishchilari almashganda FSM holati yo'qolmasligi uchun."""
    dp = Dispatcher(storage=storage or MemoryStorage())

    # Polling rejimida start_polling boshlanishida "/" menyusi o'rnatiladi
    # (webhook rejimi uchun scripts/set_webhook.py xuddi shu funksiyani chaqiradi).
    @dp.startup()
    async def _set_commands() -> None:
        try:
            await setup_bot_commands(bot)
        except Exception:
            logger.exception("Bot buyruqlar menyusini o'rnatib bo'lmadi")

    # menu/stats routerlari FSM oqimlaridan (norms, assign_task) OLDIN turadi:
    # asosiy menyu tugmasi bosilganda u FSMning "istalgan matn" bosqichiga
    # tushib qolmasdan, tegishli handlerda ushlanadi va (handler ichida
    # state.clear() bilan) chala qolgan oqimni tozalaydi.
    dp.include_router(start.router)
    dp.include_router(menu.router)
    dp.include_router(stats.router)
    dp.include_router(attendance_stats.router)
    dp.include_router(lead_stats.router)
    dp.include_router(work_schedule.router)
    dp.include_router(hourly_plan.router)
    dp.include_router(ai_watch.router)
    dp.include_router(hot_lead.router)
    dp.include_router(tasks.router)
    dp.include_router(excused.router)
    dp.include_router(work_log.router)
    dp.include_router(norms.router)
    dp.include_router(payroll.router)
    dp.include_router(admin_override.router)
    dp.include_router(mobilograf.router)
    dp.include_router(assign_task.router)
    dp.include_router(busy_period.router)
    dp.include_router(group_stats.router)
    dp.include_router(group_admin.router)
    dp.include_router(ai_center.router)
    dp.include_router(anketa.router)
    dp.include_router(knowledge.router)
    dp.include_router(playbook.router)
    dp.include_router(sales_ai.router)
    # ENG OXIRIDA ikki "erkin matn" ushlagichi, tartib muhim:
    # 1) anketa javoblari — API'da faol savol kutilmayotgan bo'lsa SkipHandler
    #    bilan keyingisiga o'tkazadi;
    # 2) AI sabab matni — yuqoridagi hech bir handler olmagan xabarlar.
    dp.include_router(anketa.answer_router)
    dp.include_router(ai_watch.reason_text_router)

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

    return dp


def allowed_update_types(dp: Dispatcher) -> list[str]:
    """Telegram'dan qaysi update turlarini so'rash. message_reaction (mobilograf)
    2-bosqichda kerak — oldindan yoqamiz, aks holda Telegram uni umuman yubormaydi."""
    types = dp.resolve_used_update_types()
    if "message_reaction" not in types:
        types = [*types, "message_reaction"]
    return types
