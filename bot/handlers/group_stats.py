from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from bot import api_client
from bot.config import TELEGRAM_GROUP_CHAT_ID, TELEGRAM_STATS_GROUP_CHAT_IDS
from bot.handlers.stats import send_global_stats

router = Router(name="group_stats")

MANAGER_ROLES = {"hr", "rop", "boss", "dasturchi"}

# /statistika asosiy guruhda ham, qo'shimcha statistika guruh(lar)ida ham ishlaydi
# (0'lar chiqarib tashlanadi — sozlanmagan guruh hech qachon mos kelmasin).
STATS_COMMAND_CHATS = {cid for cid in (TELEGRAM_GROUP_CHAT_ID, *TELEGRAM_STATS_GROUP_CHAT_IDS) if cid}


@router.message(Command("statistika"), F.chat.id.in_(STATS_COMMAND_CHATS))
async def cmd_statistika(message: Message) -> None:
    """Guruhda /statistika — kunlik yagona digestni (vazifa + qo'ng'iroq/lid/tashrif
    + AI xulosa, bitta xabar) sozlangan guruh(lar)ga darhol yuboradi (asosiy +
    qo'shimcha statistika guruhi)."""
    user = await api_client.get_user_by_telegram(message.from_user.id)
    if not user or user["role"] not in MANAGER_ROLES:
        await message.reply("Bu buyruq faqat HR/ROP/Boshliq uchun mavjud.")
        return

    await send_global_stats(message, to_group=True)


@router.message(Command("oylik"))
async def cmd_oylik(message: Message) -> None:
    """/oylik — oylik yakun digestini (joriy oy vs o'tgan oy, operator kesimida,
    bonus hisoblangan bo'lsa u ham) SHU chatga yuboradi. Faqat rahbarlar; shaxsiy
    chatda ham, guruhda ham ishlaydi."""
    user = await api_client.get_user_by_telegram(message.from_user.id)
    if not user or user["role"] not in MANAGER_ROLES:
        await message.reply("Bu buyruq faqat HR/ROP/Boshliq uchun mavjud.")
        return

    try:
        await message.bot.send_chat_action(message.chat.id, "typing")
    except Exception:  # noqa: BLE001 — chat action bezak, xatosi oqimni to'xtatmasin
        pass

    result = await api_client.trigger_monthly_digest(chat_id=message.chat.id)
    if not result.get("sent"):
        await message.reply(
            f"Oylik digestni yuborib bo'lmadi: {result.get('reason') or 'ma`lumot topilmadi'}"
        )


@router.message(Command("statistika_vaqt"))
async def cmd_statistika_vaqt(message: Message, command: CommandObject) -> None:
    """Boshliq kunlik digest (vazifa + qo'ng'iroq/lid/tashrif + AI xulosa) guruhga
    avtomatik yuboriladigan vaqtni o'zgartiradi: /statistika_vaqt 20:00.
    Argumentsiz — joriy vaqtni ko'rsatadi."""
    user = await api_client.get_user_by_telegram(message.from_user.id)
    if not user or user["role"] not in {"boss", "dasturchi"}:
        await message.reply("Vaqtni faqat Boshliq o'zgartira oladi.")
        return

    arg = (command.args or "").strip()
    if not arg:
        cur = await api_client.get_group_post_time(message.from_user.id)
        await message.reply(
            f"Kunlik digest guruhga yuboriladigan vaqt: {cur['hour']:02d}:{cur['minute']:02d}\n"
            "O'zgartirish: /statistika_vaqt 20:00"
        )
        return

    try:
        hh, mm = arg.split(":")
        hour, minute = int(hh), int(mm)
    except (ValueError, AttributeError):
        await message.reply("Format noto'g'ri. Masalan: /statistika_vaqt 20:00")
        return
    if not (0 <= hour <= 23) or not (0 <= minute <= 59):
        await message.reply("Vaqt noto'g'ri (soat 0-23, daqiqa 0-59).")
        return

    res = await api_client.set_group_post_time(message.from_user.id, hour, minute)
    if res is None:
        await message.reply("Ruxsat yo'q.")
    else:
        await message.reply(
            f"✅ Kunlik digest endi guruhga {res['hour']:02d}:{res['minute']:02d} da yuboriladi."
        )
